import numpy as np
import tkinter as tk
from tkinter import filedialog
import xml.etree.ElementTree as ET
import re
import math


def read_svg():

    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename()
    tree = ET.parse(file_path)
    root = tree.getroot()

    z_value = None
    trans_value_tuple = None

    for elem in root.iter():

        # erst hier
        if elem.tag == '{http://www.w3.org/2000/svg}g':

            z_value = elem.attrib["value"]
         
            # hole dir Transformtion für nächsten Node
            if elem.attrib["transform"] != '0':
                transformation = elem.attrib["transform"]
                transform_type = transformation.split("(")
                transform_type[1] = "(" + transform_type[1]

                if transform_type[0] == 'translate':
                    #print('translate')
                    trans_value_tuple = ('translate', transform_type[1])

                elif transform_type[0] == 'rotate':
                    #print('rotate')
                    trans_value_tuple = ('rotate', transform_type[1])

                elif transform_type[0] == 'matrix':
                    #print('matrix')
                    trans_value_tuple = ('matrix', transform_type[1])

        # dann hier
        if elem.tag == '{http://www.w3.org/2000/svg}polygon':

            pointList = []
            modified_points_string = elem.attrib["points"].replace('(', '')
            modified_points_string = modified_points_string.replace(')', '')
            splitted_poly_string = modified_points_string.split(" ")
            #splitted_poly_string = elem.attrib["points"].split(" ")

            # convertiere PolygonString zu Liste aus floats
            for i in splitted_poly_string:
                if i != '':
                    x, y = i.split(",")
                    pointList.append([float(x), float(y)])

            #print('pointList anfang: ' + str(pointList))

            # wende auf die points die entsprechende transformation an
            if trans_value_tuple != None:


                if trans_value_tuple[0] == 'translate':
                    # convertiere translateString zu floats
                    newStringXY = trans_value_tuple[1].replace('(', '')
                    newStringXY = newStringXY.replace(')', '')
                    # newString XY kann auch nur eine Komponente enthalten (Translation entlang einer Achse)
                    if "," in newStringXY:
                        x,y = newStringXY.split(",")
                        x = float(x)
                        y = float(y)
                    else:
                        x = float(newStringXY)
                        y = float(0)
     
                    for idx, i in enumerate(pointList):
                        pointList[idx][0] = i[0] + x
                        pointList[idx][1] = i[1] + y
                    print('pointList after translate: ' + str(pointList))
  
   


                elif trans_value_tuple[0] == 'rotate':
                    # make rotation operation to points
                    splitted_rotation_string = trans_value_tuple[1].replace("(", "")
                    splitted_rotation_string = splitted_rotation_string.replace(")", "")
                    splitted_rotation_string_elements = splitted_rotation_string.split(",")

                    angle        = float(splitted_rotation_string_elements[0])
                    aroundPointX = float(splitted_rotation_string_elements[1])
                    aroundPointY = float(splitted_rotation_string_elements[2])
                    cos_theta = math.cos(math.radians(angle))
                    sin_theta = math.sin(math.radians(angle))

                    for idx, i in enumerate(pointList):


                        p_x = i[0]-aroundPointX
                        p_y = i[1]-aroundPointY

                        xnew = p_x * cos_theta - p_y * sin_theta
                        ynew = p_x * sin_theta + p_y * cos_theta

                        pointList[idx][0] = xnew + aroundPointX
                        pointList[idx][1] = ynew + aroundPointY
                      

                    print('pointList after rotation: ' + str(pointList))


                elif trans_value_tuple[0] == 'matrix':
                    # make matrix operation to points with trans_value_tuple[1]
                    #print('------')
                    #print('pointList vorher: ' + str(pointList))
                    #print(trans_value_tuple[1])
                    pass
     





if __name__ == "__main__":


    read_svg()


