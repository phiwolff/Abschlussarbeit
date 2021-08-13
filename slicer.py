# -*- coding: utf-8 -*-

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
     "name": "Laser Slicer",
     "author": "Ryan Southall",
     "version": (0, 9, 2),
     "blender": (2, 80, 0),
     "location": "3D View > Tools Panel",
     "description": "Makes a series of cross-sections and exports an svg file for laser cutting",
     "warning": "",
     "wiki_url": "tba",
     "tracker_url": "https://github.com/rgsouthall/laser_slicer/issues",
     "category": "Object"}

import bpy, os, bmesh, numpy, time, shapely, pickle, os, json
from bpy.props import FloatProperty, BoolProperty, EnumProperty, IntProperty, StringProperty, FloatVectorProperty
from shapely.geometry import Point, Polygon, LineString
from operator import itemgetter
 



def newrow(layout, s1, root, s2):
    row = layout.row()
    row.label(text = s1)
    row.prop(root, s2)
    
def slicer(settings):
    dp = bpy.context.evaluated_depsgraph_get()
    f_scale = 1000 * bpy.context.scene.unit_settings.scale_length
    aob = bpy.context.active_object
    bm = bmesh.new()
    tempmesh = aob.evaluated_get(dp).to_mesh()
    bm.from_mesh(tempmesh)
    omw = aob.matrix_world
    bm.transform(omw)
    aob.evaluated_get(dp).to_mesh_clear()
    aob.select_set(False)
    mwidth = settings.laser_slicer_material_width
    mheight = settings.laser_slicer_material_height
    lt = settings.laser_slicer_material_thick/f_scale

    
    minz = min([v.co[2] for v in bm.verts]) 
    maxz = max([v.co[2] for v in bm.verts])
 
    
    # get vertice with greatest x value, from that get it's correponding z value
    verts = [vert.co for vert in bm.verts]
    z_value_motherPoly = max(verts, key = itemgetter(0))[2]  

    
    
    
    lh = minz + lt * 0.5
    ct = settings.laser_slicer_cut_thickness/f_scale
    #svgpos = settings.laser_slicer_svg_position
    dpi = settings.laser_slicer_dpi
    yrowpos = 0
    xmaxlast = 0
    ofile = settings.laser_slicer_ofile
    # umrechnungsfaktor von inch - mm ist 25,4 -> 1 inch = 25,4 mm
    mm2pi = dpi/25.4
    scale = f_scale*mm2pi
    ydiff, rysize  = 0, 0
    lcol = settings.laser_slicer_cut_colour
    lthick = settings.laser_slicer_cut_line
       
    if not any([o.get('Slices') for o in bpy.context.scene.objects]):
        me = bpy.data.meshes.new('Slices')
        cob = bpy.data.objects.new('Slices', me)
        cob['Slices'] = 1
        cobexists = 0
    else:
        for o in bpy.context.scene.objects:
            if o.get('Slices'):
                bpy.context.view_layer.objects.active = o

                for vert in o.data.vertices:
                    vert.select = True
                    
                bpy.ops.object.mode_set(mode = 'EDIT')
                bpy.ops.mesh.delete(type = 'VERT')
                bpy.ops.object.mode_set(mode = 'OBJECT')
                me = o.data
                cob = o
                cobexists = 1
                break 
            
    vlen, elen, vlenlist, elenlist = 0, 0, [0], [0]
    vpos = numpy.empty(0)
    vindex = numpy.empty(0)
    vtlist = []
    etlist = []
    vlist = []
    elist = []
    erem = []
    
    allPolys = []
    heightList = []
    polyList = []
    
    # hier wird Höhe sukezzisv erhöht
    while lh < maxz:
        cbm = bm.copy()
        newgeo = bmesh.ops.bisect_plane(cbm, geom = cbm.edges[:] + cbm.faces[:], dist = 0, plane_co = (0.0, 0.0, lh), plane_no = (0.0, 0.0, 1), clear_outer = False, clear_inner = False)['geom_cut']
     
        # sammle alle Vertices aus der Geometrie
        newverts = [v for v in newgeo if isinstance(v, bmesh.types.BMVert)] 
     
        # sammle alle Edges aus der Geometrie    
        newedges = [e for e in newgeo if isinstance(e, bmesh.types.BMEdge)]       
        
        # holde vertex mit kleinstem index
        voffset = min([v.index for v in newverts])
        # speichere vertices Koordinaten
        lvpos = [v.co for v in newverts]  
        vpos = numpy.append(vpos, numpy.array(lvpos).flatten())
        # cob.location liefert den orangen Punkt, der das Objekt reräsentiert
        # vtlist enthält alle Vertices in einer Liste, ausgehend vom Orangen Punkt der
        # die Geometrie repräsentiert
        vtlist.append([(v.co - cob.location)[0:2] for v in newverts])  
        
        # hier wird von jedem Punkt der Z-Wert der heigtList angehängt
        for v in newverts:
            heightList.append(v.co[2])


        # durchlaufe die Edges und speicher von diesen die vertices 
        # in Listen, die wiederum in der Liste etlist gespeichert werden
        # ein Element aus etlist ist eine Liste, die die beiden Vertices zu einer Edge enthält
        # Bsp eetlist = [ [(x1,y1), (x2,y2)], [(x3,y3), (x4,y4)], .... ]
        # dabei können sich edges natürlich vertices teilen
        etlist.append([[(v.co - cob.location)[0:2] for v in e.verts] for e in newedges])
        
        vindex = numpy.append(vindex, numpy.array([[v.index  - voffset + vlen for v in e.verts] for e in newedges]).flatten())

        
        vlen += len(newverts)
        elen += len(newedges)
        vlenlist.append(len(newverts) + vlenlist[-1])  
        elenlist.append(len(newedges) + elenlist[-1])
        lh += lt
        cbm.free()  
        
    bm.free()        
    me.vertices.add(vlen)
    me.vertices.foreach_set('co', vpos)
    me.edges.add(elen)
    me.edges.foreach_set('vertices', vindex)


    vranges = [(vlenlist[i], vlenlist[i+1], elenlist[i], elenlist[i+1]) for i in range(len(vlenlist) - 1)]
    vtlist = []
    etlist = []
 
    
    for vr in vranges:
        vlist, elist, erem = [], [], []
        sliceedges = me.edges[vr[2]:vr[3]]
        edgeverts = [ed.vertices[0] for ed in sliceedges] + [ed.vertices[1] for ed in sliceedges]
        edgesingleverts = [ev for ev in edgeverts if edgeverts.count(ev) == 1]
    
        # speichere die vertices, die mehr als 2 mal vorkommen
        edgeList = [ev for ev in edgeverts if edgeverts.count(ev) > 2]

        if edgeList:
            for ed in sliceedges:
                if ed.vertices[0] in edgeList and ed.vertices[1] in edgeList:
                    erem.append(ed)
             
       
        for er in erem:
            sliceedges.remove(er)
        

        vlen = len(me.vertices)
        
        if edgesingleverts:
            e = [ed for ed in sliceedges if ed.vertices[0] in edgesingleverts or ed.vertices[1] in edgesingleverts][0]
            if e.vertices[0] in edgesingleverts:
                vlist.append(e.vertices[0])
                vlist.append(e.vertices[1])
            else:
                vlist.append(e.vertices[1])
                vlist.append(e.vertices[0])
            elist.append(e)
        else:   
            elist.append(sliceedges[0]) # Add this edge to the edge list
            vlist.append(elist[0].vertices[0]) # Add the edges vertices to the vertex list
            vlist.append(elist[0].vertices[1])
            
   
 
        while len(elist) < len(sliceedges):
            va = 0
            for e in [ed for ed  in sliceedges if ed not in elist]:
                 if e.vertices[0] not in vlist and e.vertices[1] == vlist[-1]: # If a new edge contains the last vertex in the vertex list, add the other edge vertex
                     va = 1
                     vlist.append(e.vertices[0])
                     elist.append(e)
                     
                     
                     if len(elist) == len(sliceedges):
                        vlist.append(-2) 
                        
                 if e.vertices[1] not in vlist and e.vertices[0] == vlist[-1]:
                     va = 1
                     vlist.append(e.vertices[1])
                     elist.append(e)
                     
                     if len(elist) == len(sliceedges):
                        vlist.append(-2)
                        
                 elif e.vertices[1] in vlist and e.vertices[0] in vlist and e not in elist: # The last edge already has it's two vertices in the vertex list so just add the edge
                     elist.append(e)
                     va = 2
            # wenn va 0 oder 2 ist                                                              
            if va in (0, 2):
                # wenn va==0 dann hänge -2 an
                # wenn va==2 dann hänge -1 an
                vlist.append((-1, -2)[va == 0])
                
                if len(elist) < len(sliceedges):
                    try:
                        e1 = [ed for ed in sliceedges if ed not in elist and (ed.vertices[0] in edgesingleverts or ed.vertices[1] in edgesingleverts)][0]
                        if e1.vertices[0] in edgesingleverts:
                            vlist.append(e1.vertices[0])
                            vlist.append(e1.vertices[1])
                        else:
                            vlist.append(e1.vertices[1])
                            vlist.append(e1.vertices[0])
                            
                    except Exception as e:
                        e1 = [ed for ed in sliceedges if ed not in elist][0]
                        vlist.append(e1.vertices[0])
                        vlist.append(e1.vertices[1])
                    elist.append(e1)

        vtlist.append([(me.vertices[v].co, v)[v < 0]  for v in vlist])            
        etlist.append([elist]) 
        
    # an diesem Punkt liegen die Polygone in vtlist durch eine -1 separiert vor

    if os.path.isdir(bpy.path.abspath(ofile)):
        filename = os.path.join(bpy.path.abspath(ofile), aob.name+'.svg')
    else:
        filename = os.path.join(os.path.dirname(bpy.data.filepath), aob.name+'.svg') if not ofile else bpy.path.abspath(ofile)
    

    
    for vci, vclist in enumerate(vtlist):
        if vci == 0:
            svgtext = ''
            
        xmax = max([vc[0] for vc in vclist if vc not in (-1, -2)])
        xmin = min([vc[0] for vc in vclist if vc not in (-1, -2)])
        ymax = max([vc[1] for vc in vclist if vc not in (-1, -2)])
        ymin = min([vc[1] for vc in vclist if vc not in (-1, -2)])
        cysize = ymax - ymin + ct
        cxsize = xmax - xmin + ct

       
        if f_scale * (xmaxlast + cxsize) <= mwidth:
            xdiff = xmaxlast - xmin + ct
            ydiff = yrowpos - ymin + ct
            
            if rysize < cysize:
                rysize = cysize
            
            xmaxlast += cxsize
                            
        elif f_scale * cxsize > mwidth:
            xdiff = -xmin + ct
            ydiff = yrowpos - ymin + ct
            yrowpos += cysize
            if rysize < cysize:
                rysize = cysize
            
            xmaxlast = cxsize
            rysize = cysize

        else:
            yrowpos += rysize
            xdiff = -xmin + ct
            ydiff = yrowpos - ymin + ct
            xmaxlast = cxsize
            rysize = cysize
    
        
        # ------ In diesem Block werden die Shapely Polygone erzeugt ------
        
        # sorgt für Zentrierung oben links
        """
        xdiff = 0
        ydiff = 0  
        """
        # sorgt für Zentrierung in der Mitte des Materials
        xdiff = (mwidth * (scale/1000))/2
        ydiff = (mheight * (scale/1000))/2
        # hier werden die Punkte auf das svg Format skaliert
        # und die ersten beiden Punkte des Polygons werden hinzugefügt
        
        points = "{:.4f},{:.4f} {:.4f},{:.4f} ".format(scale*vclist[0][0]+xdiff, scale*vclist[0][1]+ydiff, scale*vclist[1][0]+xdiff, scale*vclist[1][1]+ydiff)
        # hier werden die folgenden Punkte betrachtet
        # else fügt Punkt hinzu wenn gültig und nur else fügt hinzu, if nicht
        # olygone werden durch -1 von einander getrennt, deshalb wird if Teil nach jeden Poylgon aufgerufen
        # dabei wird jedes Polygon zu einem Shapely Polygon gemacht und der allPolys Liste angehängt

        for vco in vclist[2:]:
            if vco in (-1, -2):
                pointsList = points.split()
                formattedList = [i.split(",") for i in pointsList]

                polygon = []
                for tuplePair in formattedList:
                    newTuple = (float(tuplePair[0]) , float(tuplePair[1]))
                    polygon.append(newTuple)


                polyList.append(polygon)
                # erzeuge Shapely polygon

                poly = Polygon(polygon)
                # füge jedes einzelne Polygon der Gesamtpolygonliste hinzu
                # Anzahl Polygone >= Anzahl Slices, da ein Slice mehrere Polygone enthalten kann
                allPolys.append(poly)
                
                # hier wird points geleert, damit für neues Polygon befüllbar ist
                points = '' 
            else:
                
                points += "{:.4f},{:.4f} ".format(scale*vco[0]+xdiff, scale*vco[1]+ydiff)
                

            
# ----- dieser Teil fügt die Slices zur Scene ----- 
    if not cobexists:
        bpy.context.scene.collection.objects.link(cob)
        
    bpy.context.view_layer.objects.active = cob
    bpy.ops.object.mode_set(mode = 'EDIT')
    bpy.ops.object.mode_set(mode = 'OBJECT')
    aob.select_set(True)
    bpy.context.view_layer.objects.active = aob


    
    i = 0
    # arrays start at 0 :)
    totalLen = -1
    
    # hier wird von jedem Polygon der z Wert ermittelt
    # polyList enthält jedes einzelne Polygon
    # wenn ein polygon X aus einem Slices die Länge n hat, dann wird in heightList die Länge n X mal eingetragen
    # Bsp. Polygon X aus erstem Slice hat Länge 3 bei einem Z Wert von 2.5
    # Polygon Y aus erstem Slice hat Länge 4 bei einem Z Wert von 2.5
    # Polygon Z aus zweiten Slice hat Länge 5 bei einem Z Wert von 4.7
    # heightList = [2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 2.5, 4.7, 4.7, 4.7, 4.7, 4.7]
    
    # polyList hat hier die gleiche Reihenfolge wie allPolys
    
    polyHeightList = []

    
    for polygon in polyList:
       
        totalLen += len(polygon)
# ----- erzeuge Tupel aus Polygonfläche und zugehörigem z Wert und füge das der polysWithHeight Liste hinzu  --------------  
        shapelyPoly = Polygon(polygon)   
        tuple = (shapelyPoly, heightList[totalLen])
        polyHeightList.append(tuple)
        
        
        
    with open(filename + '.svg', 'w') as svgfile:
        svgfile.write('<?xml version="1.0"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n\
            <svg xmlns="http://www.w3.org/2000/svg" version="1.1"\n    width="{0}"\n    height="{1}"\n    viewbox="0 0 {0} {1}">\n\
            <desc>Laser SVG Slices from Object: Sphere_net. Exported from Blender3D with the Laser Slicer Script</desc>\n\n'.format(mwidth*mm2pi, mheight*mm2pi))
            
        polyend = 'gon'
        
        #svgtext += '<!--exported_to:{0}-->\n'.format(filename)

        for node in polyHeightList:



            # value ist z Wert
            # transform wird auch 0 gesetzt um klar zu machen, dass noch keine
            # Veränderung (translation, Rotation usw) der Polygone stattgefunden hat
            # Eintrag wird bei Anwendung genannter Operationen überschrieben
            svgtext += '<g\n'
            svgtext += 'value="{0}"\n'.format(node[1])
            svgtext += 'transform="0">\n'
            #points = str(list(node.dataval[0].exterior.coords))[1:-1]
            points = str(node[0])
            points = points.replace('(' , '' )
            points = points.replace(')' , '' )
            points = points.replace('),' , '' )
            points = points.replace('POLYGON ' , '' )
            points = points.replace(' ' , ',' )
            points = points.replace(',,' , ' ' )

            print('.-.-.-.-.-.-.-.')
            print([int(255 * lc) for lc in lcol])
            print(',.,.,.,.,.,,..,')
            svgtext += '<poly{0} points="{1}" style="fill:none;stroke:rgb({2[0]},{2[1]},{2[2]});stroke-width:{3}" />\n'.format(polyend, points, [int(255 * lc) for lc in lcol], lthick)       
            svgtext += '</g>\n'
            
        
        svgfile.write(svgtext)
        svgfile.write("</svg>\n")
    
        
    # export polygon with it's z value
    data = {}
    data['infos'] = []
    data['polys'] = []
    data['motherPoly'] = []
    
    # als floatr machen
    data['infos'].append({
        'width_material': mwidth
    })
    data['infos'].append({
        'height_material': mheight
    })
    data['infos'].append({
        'mm2pi': mm2pi
    })
    
    print(lcol)
    print(type(lcol))
    data['infos'].append({
        'lcol': str(lcol)
    })   
    data['infos'].append({
        'lthick': lthick
    })
    
    for node in polyHeightList:

        # for json export scale points down to mm 
        points_list = list(node[0].exterior.coords)      
        points_list_scaled_to_mm = []

        for idx,point in enumerate(points_list):
            point = list(point)
            points_list_scaled_to_mm.append( (point[0] / mm2pi , point[1] / mm2pi) )

      

        polygon = str(points_list_scaled_to_mm)
        polygon = polygon.replace('[','')
        polygon = polygon.replace(']','')
        polygon = polygon.replace('),','')
        polygon = polygon.replace('(','')
        polygon = polygon.replace(', ',',')
        polygon = polygon.replace(')','')

        
        data['polys'].append({
            'polygon': '{0}'.format(polygon),
            'z_value': '{0}'.format(node[1])
        })
     
    data['motherPoly'].append({
        'z_value': '{0}'.format(z_value_motherPoly)
    })
    

    with open(filename + '.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
        
class OBJECT_OT_Laser_Slicer(bpy.types.Operator):
    bl_label = "Laser Slicer"
    bl_idname = "object.laser_slicer"

    def execute(self, context):
        slicer(context.scene.slicer_settings)
        return {'FINISHED'}

class OBJECT_PT_Laser_Slicer_Panel(bpy.types.Panel):
    bl_label = "Laser Slicer Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_context = "objectmode"
    bl_category = "Laser"

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        row = layout.row()
        row.label(text = "Material dimensions:")
        newrow(layout, "Thickness (mm):", scene.slicer_settings, 'laser_slicer_material_thick')
        newrow(layout, "Width (mm):", scene.slicer_settings, 'laser_slicer_material_width')
        newrow(layout, "Height (mm):", scene.slicer_settings, 'laser_slicer_material_height')
        row = layout.row()
        row.label(text = "Cut settings:")
        newrow(layout, "DPI:", scene.slicer_settings, 'laser_slicer_dpi')
        newrow(layout, "Line colour:", scene.slicer_settings, 'laser_slicer_cut_colour')
        newrow(layout, "Thickness (pixels):", scene.slicer_settings, 'laser_slicer_cut_line')
        #newrow(layout, "Separate files:", scene.slicer_settings, 'laser_slicer_separate_files')

        #if scene.slicer_settings.laser_slicer_separate_files:
        #    newrow(layout, "Cut position:", scene.slicer_settings, 'laser_slicer_svg_position')

        newrow(layout, "Cut spacing (mm):", scene.slicer_settings, 'laser_slicer_cut_thickness')
        #newrow(layout, "SVG polygons:", scene.slicer_settings, 'laser_slicer_accuracy')
        newrow(layout, "Export file(s):", scene.slicer_settings, 'laser_slicer_ofile')

        if context.active_object and context.active_object.select_get() and context.active_object.type == 'MESH' and context.active_object.data.polygons:
            row = layout.row()
            row.label(text = 'No. of slices : {:.0f}'.format(context.active_object.dimensions[2] * 1000 * context.scene.unit_settings.scale_length/scene.slicer_settings.laser_slicer_material_thick))
            
            if bpy.data.filepath or context.scene.slicer_settings.laser_slicer_ofile:
                split = layout.split()
                col = split.column()
                col.operator("object.laser_slicer", text="Slice the object")

class Slicer_Settings(bpy.types.PropertyGroup):   
    laser_slicer_material_thick: FloatProperty(
         name="", description="Thickness of the cutting material in mm",
             min=0.1, max=50, default=2)
    laser_slicer_material_width: FloatProperty(
         name="", description="Width of the cutting material in mm",
             min=1, max=5000, default=450)
    laser_slicer_material_height: FloatProperty(
         name="", description="Height of the cutting material in mm",
             min=1, max=5000, default=450)
    laser_slicer_dpi: IntProperty(
         name="", description="DPI of the laser cutter computer",
             min=50, max=500, default=96)
    laser_slicer_separate_files: BoolProperty(name = "", description = "Write out seperate SVG files", default = 0)
    #laser_slicer_svg_position: EnumProperty(items = [('0', 'Top left', 'Keep top  left position'), ('1', 'Staggered', 'Staggered position'), ('2', 'Centre', 'Apply centre position')], name = "", description = "Control the position of the SVG slice", default = '0')
    laser_slicer_cut_thickness: FloatProperty(
         name="", description="Expected thickness of the laser cut (mm)",
             min=0, max=5, default=1)
    laser_slicer_ofile: StringProperty(name="", description="Location of the exported file", default="", subtype="FILE_PATH")
    laser_slicer_accuracy: BoolProperty(name = "", description = "Control the speed and accuracy of the slicing", default = False)
    laser_slicer_cut_colour: FloatVectorProperty(size = 3, name = "", attr = "Lini colour", default = [0.0, 0.0, 0.0], subtype ='COLOR', min = 0, max = 1)
    laser_slicer_cut_line: FloatProperty(name="", description="Thickness of the svg line (pixels)", min=0, max=5, default=1)

classes = (OBJECT_PT_Laser_Slicer_Panel, OBJECT_OT_Laser_Slicer, Slicer_Settings)

def register():
    for cl in classes:
        bpy.utils.register_class(cl)

    bpy.types.Scene.slicer_settings = bpy.props.PointerProperty(type=Slicer_Settings)

def unregister():
    bpy.types.Scene.slicer_settings
    
    for cl in classes:
        bpy.utils.unregister_class(cl)



if __name__ == "__main__":
    
    register()

