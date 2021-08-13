import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
import numpy.ma as ma
from numpy.random import uniform, seed, random
import time
import math
from matplotlib.animation import FuncAnimation
import matplotlib.colors as mcolors
import shapely
from shapely.geometry import Point, Polygon, LineString 
from matplotlib.colors import LinearSegmentedColormap
import cv2
import torch
import torch.nn.functional as F
import operator
import json
from tkinter import filedialog
from decimal import Decimal
from fractions import Fraction

def toCuda(x):
	if type(x) is tuple or type(x) is list:
		return [toCuda(xi) if use_cuda else xi for xi in x]
    # creates tesors on GPU
	return x.cuda() if use_cuda else x

# hier ist dt noch nich berücksichtigt
def diffuse(T):
    T = F.conv2d(T,kernel_x,padding=[kernel_width,0])
    T = F.conv2d(T,kernel_y,padding=[0,kernel_width])
    return T


def add_gaussian(T,location,sigma=0.1,dt=1,W=50):

    #kernel = 1/(2*pi*sigma**2)*torch.exp(-((x_mesh-location[1])/sigma)**2-((y_mesh-location[0])/sigma)**2)*W*dt
    kernel = 1/(2*pi*sigma**2)*torch.exp( - ((x_mesh-location[1])**2+(y_mesh-location[0])**2)  /  (2*sigma**2) ) *W*dt
    T = T+kernel
    return T



# Wärme (K) = Energie (J) / Wärmekapazität (J/K)
# Laser Leistung (W (50W) = J/t) => W*dt = Energie (im zeitschritt dt)
# 1 Joule = 1Watt * Sekunde (Energie, die bei 1Watt in 1Sekunde umgesetzt wird)

def cool_down(T,dt=1):
	#alpha = 0.99**dt # 0.99 ~ material konstante => wieviel energie wird an umgebung abgegeben (pro zeit)
	k = torch.tensor(0.01)
	alpha = torch.exp(-k*dt)
	T_env = 0
    # je größer der Zeitschritt, desto kleiner alpha, desto größer der Einfluss der Umgebungstemp. und geringer der Einfluss der vorhandenen Temp auf Grid
	T = T*alpha+(1-alpha)*T_env
	return T


def render_loop(optList, configuration, path_file):
    material_width  = 0
    material_height = 0
    with open(path_file) as json_file:
        data = json.load(json_file)
        material_width = data['infos'][0]['width_material']
        material_height = data['infos'][1]['height_material']

    config = configuration


    t = 0
    dt = config.get('processing_settings')["laser_settings"]["dt"]
    laser_power = config.get('processing_settings')["laser_settings"]["power"]
    global init_speed
    init_speed = config.get('processing_settings')["laser_settings"]["speed"]
    factor_temp_from_energie = config.get('processing_settings')["simulation_settings"]["factor_temp_from_energie"]
    threshold_speed_increase = config.get('processing_settings')["simulation_settings"]["threshold_speed_increase"]
    conv_kernel = config.get('processing_settings')["simulation_settings"]["conv_kernel"]
    global kernel_width
    kernel_width = config.get('processing_settings')["simulation_settings"]["kernel_width"]
    global use_cuda
    use_cuda = config.get('processing_settings')["simulation_settings"]["use_cuda"]
    timesteps_per_frame = config.get('processing_settings')["simulation_settings"]["timesteps_per_frame"]
    global sigma 
    sigma = config.get('processing_settings')["laser_settings"]["sigma"]
    global pi
    pi = 3.14159265359
    dx = config.get('processing_settings')["dx"]
    x_range = torch.arange(0,material_width,dx)
    y_range = torch.arange(0,material_height,dx)
    global x_mesh, y_mesh
    x_mesh, y_mesh = toCuda(torch.meshgrid(x_range,y_range))
    global T
    T = toCuda(torch.zeros_like(x_mesh).unsqueeze(0).unsqueeze(1).float())
    global overlap
    overlap = False
    global percentage
    percentage = 0 

    global  kernel_x, kernel_y
    kernel = torch.tensor(conv_kernel)
    kernel /= torch.sum(kernel) # normalize; get weighted kernel 
    kernel_x = toCuda(kernel.unsqueeze(0).unsqueeze(1).unsqueeze(3))# kernel in x direction
    kernel_y = toCuda(kernel.unsqueeze(0).unsqueeze(1).unsqueeze(2))# kernel in y direction

    cv2.namedWindow('T',cv2.WINDOW_NORMAL)
    addedPolys = 0
    i = 0

    operator_look_up = {
        '>': operator.gt,
        '<': operator.lt
    }

    old_speed = toCuda(torch.zeros(1))
    counter = 0
    last_temp = toCuda(torch.zeros(1))
    highest_temp = toCuda(torch.zeros(1))
    location_speed_list = []

    fac = 0
    fac = float(np.reciprocal(Fraction(Decimal(dx))))
 

    with torch.no_grad():
        for poly in optList:
            location_speed_single_poly_list = []
            vetices_poly = poly.dataval[0].exterior.coords[:]
            number_points_poly = len(vetices_poly)
            sign_poly = poly.sign
            # the start element of a segment is always the start_vertex
            x_t = toCuda(torch.zeros(2))
            x_t[0] = vetices_poly[0][0]
            x_t[1] = vetices_poly[0][1]

            x_x_t = (round((x_t)[0].item(),1) * fac) / fac
            y_x_t = (round((x_t)[1].item(),1) * fac) / fac
            temperature = T[0,0,   int(x_x_t /dx), int(y_x_t /dx)  ]


            #temperature = T[0,0, int(torch.round(x_t)[0].item()), int(torch.round(x_t)[1].item())]
            #temperature = T[0,0, int(x_t[0].item()/dx), int(x_t[1].item()/dx)]
            new_speed = get_speed_from_temperature(temperature*factor_temp_from_energie, threshold_speed_increase) 
            # evtl. hier speed auf None setzten um klar zu machen, dass mit G0 (direkter Weg) gefahren werden soll
            location_speed_single_poly_list.append( (x_t.tolist(), new_speed.tolist(), laser_power, sign_poly) )
         

            for idx_vertex,vertex in enumerate(vetices_poly):           

                if idx_vertex < number_points_poly - 1:
                    # calc direction vector of every segment
                    start_segment       = vertex
                    end_segment         = vetices_poly[idx_vertex+1] 
                    direction_vector    = toCuda(torch.zeros(2))
                    direction_vector[0] = end_segment[0] - start_segment[0]
                    direction_vector[1] = end_segment[1] - start_segment[1]    
                    normalize           = torch.sqrt(  (torch.pow(direction_vector[0],2) + torch.pow(direction_vector[1],2) ) )
                    direction_vector[0] = direction_vector[0] / normalize
                    direction_vector[1] = direction_vector[1] / normalize

                    # round, otherwise there are numbers close to zero which leads to errors in operator assignment
                    x = round(direction_vector[0].item(),4)
                    y = round(direction_vector[1].item(),4)
                    direction_vector[0] = x
                    direction_vector[1] = y

                    which_op_x = None
                    which_op_y = None
                    op_x       = None
                    op_y       = None

                    # check which are the bounds for points set by direction_vector until they reach end of segment

                    if direction_vector[0] != 0:
                        if direction_vector[0] < 0:
                            which_op_x = '>'
                        elif direction_vector[0] > 0:
                            which_op_x = '<'                  
                    if direction_vector[0] == 0:
                        which_op_x = None
                    if direction_vector[1] != 0:
                        if direction_vector[1] < 0:
                            which_op_y = '>'
                        elif direction_vector[1] > 0:
                            which_op_y = '<'
                    if direction_vector[1] == 0:
                        which_op_y = None                   
                    if which_op_x != None:
                        op_x = operator_look_up.get(which_op_x)
                    if which_op_y != None:
                        op_y = operator_look_up.get(which_op_y)

   
                    while True:
                        # as long as end of segment is not reached
      
                        if ( op_x != None and op_y != None and op_x(x_t[0].item(),end_segment[0]) and op_y(x_t[1].item(), end_segment[1]) ) \
                            or (   op_x == None and op_y != None and op_y(x_t[1].item(), end_segment[1]) ) \
                            or (   op_x != None and op_y == None and  op_x(x_t[0].item(), end_segment[0]) ):

                            # look temp up at current laser_position (round indices because there are no values between to index)          

                            if overlap == False:
                                dt = config.get('processing_settings')["laser_settings"]["dt"]
                                x_x_t = (round((x_t)[0].item(),1) * fac) / fac
                                y_x_t = (round((x_t)[1].item(),1) * fac) / fac
                                temperature = T[0,0,   int(x_x_t /dx), int(y_x_t /dx)  ]     
                                new_speed = get_speed_from_temperature(temperature*factor_temp_from_energie, threshold_speed_increase)    
                                T = add_gaussian(T,x_t,sigma,dt,laser_power)   
                                old_speed = new_speed
                                old_x_t = x_t

                                # update x_t
                                v_t = toCuda(torch.zeros(2))
                                v_t[0] = direction_vector[0] * new_speed
                                v_t[1] = direction_vector[1] * new_speed 
                                x_t = x_t + dt * v_t     
   

                            # points can overlap the end_segment
                            # make sure to add vertex and add next point with overlap on new segment
                            # garantuees that dt is constant 
                            if overlap == True:
                                # add end_segment corresponding to percantage to end_segment
                                T = add_gaussian(T,x_t,sigma,dt,laser_power) 
                                dt = config.get('processing_settings')["laser_settings"]["dt"]
                                v_t = toCuda(torch.zeros(2))
                                v_t[0] = direction_vector[0] * old_speed
                                v_t[1] = direction_vector[1] * old_speed 
                                
                                x_t = x_t + dt * v_t 
                                #T = add_gaussian(T,x_t,3,dt,laser_power)   
                                dt = config.get('processing_settings')["laser_settings"]["dt"]
                                overlap = False



                            # add new point with speed to it to list if new point is not outside bouns (this is relevant for gcode export)
                            # check a second time here, because x_t is modified after last check for condition
                            if ( op_x != None and op_y != None and op_x(x_t[0].item(),end_segment[0]) and op_y(x_t[1].item(), end_segment[1]) ) \
                                or (   op_x == None and op_y != None and op_y(x_t[1].item(), end_segment[1]) ) \
                                or (   op_x != None and op_y == None and  op_x(x_t[0].item(), end_segment[0]) ):

                                location_speed_single_poly_list.append( (x_t.tolist(), new_speed.tolist(), laser_power, sign_poly) )

                            t += dt
                            i += 1
                
                            T = diffuse(T)
                            T = cool_down(T,dt)

                            
                            

                            if i % timesteps_per_frame == 0:
                                image = T[0,0].cpu().detach().clone()
                                image = image - torch.min(image)
                                #print('torch.min(image) ' + str(torch.min(image)))
                                image /= torch.max(image)
                                #print('torch.max(image) ' + str(torch.max(image)))
                                #backtorgb = cv2.cvtColor(image.numpy(),cv2.CV_GRAY2RGB)
                                #cv2.imshow('T',backtorgb)
                                cv2.imshow('T',image.numpy())
                                cv2.waitKey(1)

                        # new point is beyound bounds
                        else:     
                            distance_x_t_overlap_x = abs(old_x_t[0] - x_t[0])
                            distance_x_t_overlap_y = abs(old_x_t[1] - x_t[1])
                            distance_x_t_correct_x = abs(old_x_t[0] - end_segment[0])
                            distance_x_t_correct_y = abs(old_x_t[1] - end_segment[1])
                            distance_overlap = torch.sqrt( torch.pow(distance_x_t_overlap_x,2) + torch.pow(distance_x_t_overlap_y,2) )
                            distance_correct = torch.sqrt( torch.pow(distance_x_t_correct_x,2) + torch.pow(distance_x_t_correct_y,2) )
                            percentage = distance_correct / distance_overlap
                            overlap = True
                            dt = dt*percentage.item()
                            # set new point as end_segment
                            x_t[0] = end_segment[0]
                            x_t[1] = end_segment[1]    
                            
                            # only add this gaussian if last segment of a poly is reached
                            if idx_vertex == number_points_poly - 2:
                                T = add_gaussian(T,x_t,sigma,dt,laser_power)
                                dt = config.get('processing_settings')["laser_settings"]["dt"]
                                overlap = False
                                print('last add_gaussian of a poly')


                            # muss hier nicht auch noch new_speed für den nöchsten Punkt ausgerechnet werden ???
                            # hier nicht einfach nur alten speed anhängen sondern skaliert auf die kürzere strecke verschnellern
                            location_speed_single_poly_list.append( (x_t.tolist(), old_speed.tolist(), laser_power, sign_poly) )
                            break

            
            location_speed_list.append(location_speed_single_poly_list)

    return location_speed_list

def get_speed_from_temperature(temp, threshold):
    global init_speed
    # don't change speed
    if temp <= threshold:
        return toCuda(torch.tensor(init_speed))

    else:
        # m * x + n
        return toCuda(torch.tensor(1.2*temp+init_speed))
          


def make_json(data_list, path_to_save_location, min_cutting_list):

    # export paths of polygons as json with speed at location X,Y

    # to do: add min cutting list at end of all
    data = {}
    data['polygons'] = []
    data['cut_polygons'] = []

    for poly in data_list:
        data['polygons'].append( {'polygon': [point for point in poly]   } )

    

    for cut_node in min_cutting_list:
        #print(cut_node.dataval[0])
        data['cut_polygons'].append( {'polygon_cut': list(cut_node.dataval[0].exterior.coords)   } )



    #with open(filename + '.json', 'w', encoding='utf-8') as f:
    
    with open(path_to_save_location + '.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    f.close()


def make_gcode(path_to_save_location, conf):

    cnt = 0
    poly_and_height_list = []
    cut_out_speed = conf.get('processing_settings')['opt']['cut_out_speed']
    cut_out_power = conf.get('processing_settings')['opt']['cut_out_power']


    with open(path_to_save_location + '.json') as json_file:
        data = json.load(json_file)
        # list which's entries look like :  ([x,y], speed, power)

        f = open(path_to_save_location + ".g", "w")
        f.write("%\n")
        f.write("G21 G17 G90 \n")
        for polygon in data['polygons']:
            for idx, point_data in enumerate(polygon['polygon']):
                # rapid move to start point of new polygon
                if idx == 0:  
                    
                    f.write("S0\n")
                    f.write("G0 X{0} Y{1}\n".format(point_data[0][0], point_data[0][1]))
                    # convert 0-100W to 0-255
                    f.write("S{0}\n".format( int(((point_data[2]-0)/(100-0)) * (255-0) + 0 )))
                # controlled movement to specified point
                else:
                    f.write("G1 X{0} Y{1} F{2}\n".format(point_data[0][0], point_data[0][1], point_data[1]))
         
        # add cut out polys to gcode
        len_cut_polygons = len(data['cut_polygons'])
        for outer_idx, cut_poly in enumerate(data['cut_polygons']):
            len_cut_poly = len(cut_poly['polygon_cut'])
            for idx, point_data in enumerate(cut_poly['polygon_cut']):
                if idx == 0:
                    f.write("G0 X{0} Y{1} F{2}\n".format(point_data[0], point_data[1], cut_out_speed))
                else:
                    f.write("G1 X{0} Y{1} F{2}\n".format(point_data[0], point_data[1], cut_out_speed))
                if idx < len_cut_poly-1 or outer_idx != len_cut_polygons-1:
                    f.write("S{0}\n".format(cut_out_power))

        f.write("M30\n")
        f.write("%")
        f.close()


    return 


def main(config, optList, minCutting, path_to_file):

    # path_to_file holds information from slicer.py about the material_size
    speed_at_location_list = render_loop(optList, config, path_to_file)
    print('Wohin soll die json und die gcode Datei exportiert werden?')
    file_path = filedialog.asksaveasfilename()
    make_json(speed_at_location_list, file_path, minCutting)
    make_gcode(file_path, config)