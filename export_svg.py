import json



def make_svg(optList, path_to_file):

    # read json from exported from slicer.py to create svg file with the optimized sign order of the polygons
    # svg file is created in the same directory where the json from slicer.py is exported to
    mwidth = None
    mheight = None
    mm2pi = None
    lcol = None
    lthick = None
    svgtext = ''


    with open(path_to_file) as json_file:
        data = json.load(json_file)
        mwidth = data['infos'][0]['width_material']
        mheight = data['infos'][1]['height_material']
        mm2pi = data['infos'][2]['mm2pi']
        lcol = data['infos'][3]['lcol']
        lthick = data['infos'][4]['lthick']


    lcol = lcol.split()
    lcol = lcol[1:]
    red = float(lcol[0][3:-1])
    green = float(lcol[1][2:-1])
    blue  = float(lcol[2][2:-2])
    lcol = []
    lcol.append(red)
    lcol.append(green)
    lcol.append(blue)

    path_to_file = path_to_file[:-5]

    with open(path_to_file + '_opt.svg', 'w') as svgfile:
            svgfile.write('<?xml version="1.0"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n\
                <svg xmlns="http://www.w3.org/2000/svg" version="1.1"\n    width="{0}"\n    height="{1}"\n    viewbox="0 0 {0} {1}">\n\
                <desc>Laser SVG Slices from Object: Sphere_net. Exported from Blender3D with the Laser Slicer Script</desc>\n\n'.format(mwidth*mm2pi, mheight*mm2pi))
            
            for node in optList:

                svgtext += '<g\n'
                svgtext += 'transform="0">\n'
                scaled_points = []
                points = [p[0] * mm2pi for p in node.dataval[0].exterior.coords[:]]
                for idx,p in enumerate(node.dataval[0].exterior.coords[:]):
                    scaled_points.append((p[0] * mm2pi, p[1]*mm2pi))

                points = str(scaled_points)
                points = points.replace('[' , '' )
                points = points.replace(']' , '' )
                points = points.replace('(,' , '' )
                points = points.replace('(' , '' )
                points = points.replace('),' , '' )
                points = points.replace(')' , '' )
               
                svgtext += '<polygon points="{0}" style="fill:none;stroke:rgb({1[0]},{1[1]},{1[2]});stroke-width:{2}" />\n'.format(points, [int(255 * lc) for lc in lcol], lthick)
                svgtext += '</g>\n'
            
        
            svgfile.write(svgtext)
            svgfile.write("</svg>\n")

def main(optList,file_path):

    make_svg(optList,file_path)