 # -*- coding: utf-8 -*-
import sys
import tkinter as tk
import json
import shapely
import yaml
from shapely.geometry import Point, Polygon, LineString 
from tkinter import filedialog
from operator import itemgetter
import time

class Node:
    def __init__(self, value=None, s=None):
        # dataval enthält Tupel (Polygon, Fläche, z Wert) enthalten
        self.dataval = value
        self.parent = None
        self.leftChild = []
        self.rightChild = []
        self.sign = s
        self.positionInList = None
        self.dependenciesRight = None
        self.dependenciesLeft = None


def getData(file_path):

    cnt = 0
    poly_and_height_list = []
    with open(file_path) as json_file:
        data = json.load(json_file)
        for p in data['polys']:
            # füge das Tupel Polygon und dessen z-Wert der Liste hinzu
            polygon = p['polygon'].replace("'", "")
            # erhalte x,y Pärchen
            formattedPolygon = polygon.split(" ")
            formattedPoints  = []
            for point in formattedPolygon:
                x, y = point.split(",")
                x    = float(x)
                y    = float(y)
                formattedPoints.append((x, y))
                
            poly = Polygon(formattedPoints)
            z_value = float(p['z_value'].replace("'", ""))
            poly_and_height_list.append((poly, poly.area, z_value))

        motherPoly_z_value = float(data['motherPoly'][0]['z_value'])

    return poly_and_height_list, motherPoly_z_value


def sortData(data):
    """
    sorts area data in descending order 
    :return: sorted list
    """
    data.sort(key=itemgetter(1), reverse=True)
    return data

def makeNodes(sortedList): 
    """
    creates List of nodes
    :param sortedList: list of tuples ordered in descending order regarding area
    """

    nodeList = []
    for n in sortedList:
        nodeList.append(Node(n, None))
    return nodeList


def buildTrees(nodeList, mother_poly_z):
    """
    build trees from nodeList
    :return: list of trees
    """
    treeList            = []
    addedNodes          = 0
    nodeListLen         = len(nodeList)

    #while addedNodes < nodeListLen:
    while len(nodeList) > 0:
        # build tree from nodeList
        # nodes added to a tree X get deleted from nodeList, since they're no longer relevant
        tree        = buildTree(nodeList,mother_poly_z)
        addedNodes += len(tree) 
        nodeList    = [node for node in nodeList if node not in tree]
        treeList.append(tree)


    return treeList



def buildTree(listOfNodes, z_value_mother_poly):

    # in slicer.py wird motherPoly ermittelt, anhand von diesem kann für jedes polygon ein vorzeichen vergeben werden
    treeX               = []
    nodeListWithRoot    = listOfNodes.copy()
    # roots also get signs
    # error if not. sign flip below assigns "checkNode.sign = not(previousNode.sign)". not(None) results in True which could be a false value
    if nodeListWithRoot[0].dataval[2] < z_value_mother_poly:
        nodeListWithRoot[0].sign = False
    elif nodeListWithRoot[0].dataval[2] > z_value_mother_poly:
        nodeListWithRoot[0].sign = True
    root                = listOfNodes.pop(0)
    lenListOfNodes      = len(listOfNodes)
    addedNodes          = 0
    do_not_consider_list = []
  
    # loop though listOfNodes and check if Nodes with smaller area are within previous added nodes
    for idx, checkNode in enumerate(listOfNodes):
        # from current node run backwards and check if previous nodes contain checkNode(is current Node)
        for previousNode in nodeListWithRoot[idx::-1]:
            if checkNode.dataval[0].within(previousNode.dataval[0]) and previousNode not in do_not_consider_list:
                # check z value for sign and give relationship
                if checkNode.dataval[2] > previousNode.dataval[2]:
                    checkNode.sign   = True
                    previousNode.leftChild.append(checkNode)
                    checkNode.parent = previousNode
                elif checkNode.dataval[2] < previousNode.dataval[2]:
                    checkNode.sign = False
                    previousNode.rightChild.append(checkNode)
                    checkNode.parent = previousNode
                # nodes on same z level -> sign flip
                else:
                    # note: not(None) -> True
                    checkNode.sign = not(previousNode.sign)
                    if checkNode.sign == True:
                        previousNode.leftChild.append(checkNode)
                    elif checkNode.sign == False:
                        previousNode.rightChild.append(checkNode)
                    checkNode.parent = previousNode
                treeX.append(checkNode)
                break

            # if first node is reached and none of the nodes containing checkNode
            # it has to be a root of another tree, so compare to motherpoly to give sign
            # also don't consider this node for following relations -> this happens in another loop 
            elif previousNode == nodeListWithRoot[0]:
                if checkNode.dataval[2] < z_value_mother_poly:
                    checkNode.sign = False
                elif checkNode.dataval[2] > z_value_mother_poly:
                    checkNode.sign = True
                                
                elif checkNode.dataval[2] == z_value_mother_poly:
                    print('------------------ dieser Fall kann auftreten !!!!! ------------------')


                do_not_consider_list.append(checkNode)

    # give root None sign -> mark as node relevant for calculation of all enclosing root polygon
    # parent of a root is None -> check later in optimize algo

    nodeListWithRoot[0].parent = None
    treeX.insert(0, nodeListWithRoot[0])

    for n in treeX:
        n.dependenciesRight = len(n.rightChild)
        n.dependenciesLeft  = len(n.leftChild)

    return treeX



def makeMasterRoot(listOfTrees, z_value_motherPoly, processing_settings_data):
    """
    build one all enclosing polygon to be the root of all trees if more than one tree.
    This gives sign to every root of tree which has this point has sign=None
    :return: list of Trees and masterRoot
    """
    # identify the bounds of all polys together to make one all enclosing polygon
    # modify abs values so that they are defently enclosing everythin (add or substract from reults) 

    abs_min_x      = None
    abs_min_y      = None
    abs_max_x      = None
    abs_max_y      = None


    cut_out_distance = processing_settings_data['opt']['cut_out_distance']
    
    if len(listOfTrees) > 1:
        z_value_list = []
        for tree in listOfTrees:

            # calc absolut min and max for x,y to get all enclosing bb
            min_x, min_y, max_x, max_y = tree[0].dataval[0].bounds
            z_value_list.append(tree[0].dataval[1])
            # for first iteration take values of first polygon
            if all(v is None for v in[abs_min_x, abs_min_y, abs_max_x, abs_max_y]):
                abs_min_x, abs_min_y, abs_max_x, abs_max_y = min_x, min_y, max_x, max_y
            # abs_x_x should always be the best in it's game
            if min_x < abs_min_x:
                abs_min_x = min_x
            if min_y < abs_min_y:
                abs_min_y = min_y
            if max_x > abs_max_x:
                abs_max_x = max_x
            if max_y > abs_max_y:
                abs_max_y = max_y

        # scale moterPoly 
        abs_min_x -= cut_out_distance
        abs_min_y -= cut_out_distance
        abs_max_x += cut_out_distance
        abs_max_y += cut_out_distance      

        motherPoly      = Polygon([(abs_min_x, abs_min_y), (abs_max_x, abs_min_y), 
                                  (abs_max_x, abs_max_y), (abs_min_x, abs_max_y)])
        motherPoly_area = motherPoly.area
        motherPoly_z    = z_value_motherPoly
        rootTuple       = (motherPoly, motherPoly_area, motherPoly_z)
        newRootNode     = Node(rootTuple, None)


        # append old roots in correct way to new motherPoly and give old roots signs

        for tree in listOfTrees:

            if newRootNode.dataval[2] < tree[0].dataval[2]:
                tree[0].sign   = True
                tree[0].parent = newRootNode
                newRootNode.leftChild.append(tree[0])
            
            elif newRootNode.dataval[2] > tree[0].dataval[2]:
                tree[0].sign   = False
                tree[0].parent = newRootNode
                newRootNode.rightChild.append(tree[0])

            else:
                print('Error: Fehler beim slicing; kann nicht weiter verarbeiten')

        return listOfTrees, newRootNode


    elif len(listOfTrees) == 1:

        root = listOfTrees[0][0]

        min_x, min_y, max_x, max_y = root.dataval[0].bounds
        
        abs_min_x = min_x
        abs_min_y = min_y
        abs_max_x = max_x
        abs_max_y = max_y

        # scale moterPoly 
        abs_min_x -= cut_out_distance 
        abs_min_y -= cut_out_distance
        abs_max_x += cut_out_distance
        abs_max_y += cut_out_distance   

        # create motherPoly, insert it and handle relationship to old root
        motherPoly         = Polygon([(abs_min_x, abs_min_y), (abs_max_x, abs_min_y), 
                                      (abs_max_x, abs_max_y), (abs_min_x, abs_max_y)])
        motherPoly_area    = motherPoly.area
        motherPoly_z       = z_value_motherPoly
        rootTuple          = (motherPoly, motherPoly_area, motherPoly_z)
        newRootNode        = Node(rootTuple, None)
        listOfTrees[0][0].parent = newRootNode

        if newRootNode.dataval[2] < listOfTrees[0][0].dataval[2]:
            listOfTrees[0][0].sign = True
            newRootNode.leftChild.append(listOfTrees[0][0])
        elif newRootNode.dataval[2] > listOfTrees[0][0].dataval[2]:
            listOfTrees[0][0].sign = False
            newRootNode.rightChild.append(listOfTrees[0][0])
        else: 
            print('Error: Fehler beim slicing; kann nicht weiter verarbeiten')

        


        
        return listOfTrees, newRootNode


    else:
        print('Liste ist leer')

    


def initNoDepsList(treeList):
    # save leafs in noDepsList
    noDepsList = []
    for tree in treeList:
        for node in tree:
            if len(node.rightChild) == 0 and len(node.leftChild) == 0:
                noDepsList.append(node)
    return noDepsList

def sortNoDepsListArea(noDepsList):
    # sort area ascending

    # sort area ascending for positive sign and negative sign -> two ascending lists
    # from those two lists make two other lists: one starting with positive sign the other with negative
    # run opt algo with both lists and count sign changes of two resulting optLists -> take the one with less sign changes
    noDepsList.sort(key = lambda n: n.dataval[1], reverse=False)
    return noDepsList



def findOutFirstElement(pos_tree_list, neg_tree_list, treeList_data):

    # create treeList copies, calc which option has less sign changes and return number of sign changes for each option (pos and neg)
    pos_sign_changes = solve_pos_neg_opt(pos_tree_list, True, True)
    neg_sign_changes = solve_pos_neg_opt(neg_tree_list, False, True)


    # decide based on number of sign changes (calced with first def solve_pos_neg_opt call)
    # if pos or neg starting sign list is returned
    if pos_sign_changes <= neg_sign_changes:
        start_positive_no_deps_list = solve_pos_neg_opt(treeList_data, True, False)
        return start_positive_no_deps_list
    else: 
        start_negative_no_deps_list = solve_pos_neg_opt(treeList_data, False, False)
        return start_negative_no_deps_list


def solve_pos_neg_opt(treeList_data, sign, calc_opt):

    noDepsList_init     =   initNoDepsList(treeList_data)
    noDepsList_sorted   =   sortNoDepsListArea(noDepsList_init)


    shortest_distance_positive = None
    shortest_distance_negative = None
    positive_no_deps_list = []
    negative_no_deps_list = []
    poly_with_shortest_distance_positive = None
    poly_with_shortest_distance_negative = None
    origin = Point(0,0)

    #check which point with positive sign is the clostest to the origin(0,0)
    for n in noDepsList_sorted:
        if n.sign == True:
            positive_no_deps_list.append(n)
            first_point_poly = Point(n.dataval[0].exterior.coords[0])
            distance = first_point_poly.distance(origin)
            if shortest_distance_positive == None:
                    shortest_distance_positive = distance 
                    poly_with_shortest_distance_positive = n
            if distance < shortest_distance_positive:
                    shortest_distance_positive = distance
                    poly_with_shortest_distance_positive = n
        if n.sign == False:
            negative_no_deps_list.append(n)
            first_point_poly = Point(n.dataval[0].exterior.coords[0])
            distance = first_point_poly.distance(origin)
            if shortest_distance_negative == None:
                    shortest_distance_negative = distance 
                    poly_with_shortest_distance_negative = n
            if distance < shortest_distance_negative:
                    shortest_distance_negative = distance
                    poly_with_shortest_distance_negative = n

    if len(positive_no_deps_list) > 0:
        positive_no_deps_list.remove(poly_with_shortest_distance_positive)
        positive_no_deps_list.insert(0,poly_with_shortest_distance_positive)
        
    if len(negative_no_deps_list) > 0:
        negative_no_deps_list.remove(poly_with_shortest_distance_negative)
        negative_no_deps_list.insert(0,poly_with_shortest_distance_negative)

    no_deps_list = []

    if sign == True:
        no_deps_list  =  positive_no_deps_list
        no_deps_list +=  negative_no_deps_list
    if sign == False:
        no_deps_list  =  negative_no_deps_list
        no_deps_list +=  positive_no_deps_list

    if calc_opt == True:
        # find out if starting with positive sign or starting with negative sign has a the less sign changes and return the one with min
        # sign changes
        finalOptList, cutOutList_pos = startAddingNodes(no_deps_list)

        last_sign = None
        sign_changes = 0
        for n in finalOptList:
            if last_sign == None:
                last_sign = n.sign
            if last_sign != n.sign:
                sign_changes += 1
            last_sign = n.sign
          
        return sign_changes

    if calc_opt == False:
        return no_deps_list



def findNextNode(noDepsList, currentNode, mode, swapSign):

    betterCanidateFound         = False
    smallestDistance            = None
    greatestDistance            = None
    # check which sign to search for
    if not(swapSign):
        signToCheck                 = currentNode.sign
    else:
        signToCheck                 = not(currentNode.sign)


    # form current node check all remaining nodes for smallest distance (greedy algo)
    firstPointCurrentNode = Point(currentNode.dataval[0].exterior.coords[0])
    # mode 1
    if mode == 1:
        for n in noDepsList:
            if signToCheck == n.sign:
                # check first point of each poly, because laser starts and ends here              
                firstPointN           = Point(n.dataval[0].exterior.coords[0])
                distance = firstPointCurrentNode.distance(firstPointN)
                if smallestDistance == None:
                    smallestDistance = distance 
                if distance <= smallestDistance:
                    smallestDistance = distance
                    betterCanidateFound = True
                    currentNode = n

    # mode 2 (# form current node check all remaining nodes for greatest distance (greedy algo))
    if mode == 2:
        for n in noDepsList:
            if signToCheck == n.sign:             
                firstPointN           = Point(n.dataval[0].exterior.coords[0])
                distance = firstPointCurrentNode.distance(firstPointN)
                if greatestDistance == None:
                    greatestDistance = distance 
                if distance >= greatestDistance:
                    greatestDistance = distance
                    betterCanidateFound = True
                    currentNode = n
                        

    return currentNode, betterCanidateFound



def searchNode(noDepsList, currentNode, savePot):


    nodesToAdd        = 0
    terminateWhile    = False
    if savePot:
        currentNodePot = currentNode.parent
    else:
        currentNodePot = None
    # Mode 1: check if nearest node with same sign to last node added to optList exists
    if processing_settings['opt']['smallest_distance']:
        currentNodeFound, betterCanidateFound = findNextNode(noDepsList, currentNode, 1, False)
    # mode 2
    else:
        currentNodeFound, betterCanidateFound = findNextNode(noDepsList, currentNode, 2, False)

    if betterCanidateFound == True:
        if currentNodePot != None:
            noDepsList.append(currentNodePot)
            nodesToAdd += 1 
        currentNode = currentNodeFound
        nodesToAdd += 1
    else:
        if currentNodePot != None:
            currentNode = currentNodePot
            nodesToAdd += 1
        else:
            currentNodeFound, betterCanidateFound = findNextNode(noDepsList, currentNode, 1, True)
            if betterCanidateFound:
                currentNode = currentNodeFound
                nodesToAdd += 1
            # terminate 
            else:
                terminateWhile = True


    return currentNode, noDepsList, terminateWhile, nodesToAdd

def startAddingNodes(noDepsList_data):  

    # add first element of noDepsList to optList
    # check if parent node of this node can be added
    # if yes: add it to optList
    # if no, because different sign: put into noDepsList in the right place
    # if no, because more than on dependency, look which node in noDepsList has the same
    #               sign like the last added and has min distance to it
    #               if there is no node with same sign which can be added: look if parent has 
    #               0 deps
    #               if it has more than 0 deps: look which node in noDepsList of different sign
    #               with smallest distance can be added
    # :returns: remaining noDepsList. Elements are canidates which couldn't be added, because of dependencies
         
    noDepsList    = noDepsList_data.copy()
    currentNode   = noDepsList[0]
    nodesToAdd    = len(noDepsList)
    terminate     = False
    cnt           = 0
    optList       = []
    cutOutList    = []

    while nodesToAdd > 0:
        cnt   += 1
        addLen = None
        optList.append(currentNode) 
        backUpNode = currentNode
        if currentNode in noDepsList:
            noDepsList.remove(currentNode)
            nodesToAdd -= 1               
        # check if parent node exists and delete dependency to just added child node
        if currentNode.parent != None:
            if currentNode in currentNode.parent.rightChild:
                currentNode.parent.rightChild.remove(currentNode)
            if currentNode in currentNode.parent.leftChild:
                currentNode.parent.leftChild.remove(currentNode)
            # if parent node has 0 dependencies
            if not currentNode.parent.rightChild and \
                not currentNode.parent.leftChild:
                # if parent node has same sign    
                if currentNode.sign == currentNode.parent.sign:
                    currentNode = currentNode.parent
                    nodesToAdd += 1
                # if parent doesn't have same sign 
                else:
                    # do not save parent node as potCanidate, 
                    # add it instead to cutOutList (it's a root of af a tree, which is used for cutting)
                    # and search somewhere else for a node to proceed
                    if currentNode.parent.sign == None:
                        if currentNode.parent not in cutOutList:
                            cutOutList.append(currentNode.parent)
                        currentNode, noDepsList, terminate, addLen = searchNode(noDepsList, currentNode, False)

                    # save parent Node as potential canidate
                    else:
                        currentNode, noDepsList, terminate, addLen = searchNode(noDepsList, currentNode, True)

            #parent has more than 0 dependencies
            else:
                currentNode, noDepsList, terminate, addLen = searchNode(noDepsList, currentNode, False) 
                                                        
        #parent doesn't exist
        else:
            currentNode, noDepsList, terminate, addLen = searchNode(noDepsList, currentNode, False) 

        if terminate:
            return optList, cutOutList
            break

        if addLen != None:
            nodesToAdd += addLen





def calcCuttingOrder(lastElement, cuttingList):
    """
    param: lastElement: last node in finalOptList (this is the last path the laser is forming before cutting)
    param: cuttingList: list of roots for cutting (list gets sorted by this function to reduce distance laser has to move)
    return: order list of cutting paths
    """

    lastPointForming = Point(lastElement.dataval[0].exterior.coords[0])
    lastPointAdded   = lastPointForming
    lastNodeAdded    = lastElement
    nearestPoint        = None
    minDistanceCutting  = []
    lenCuttingList      = len(cuttingList)
        
    while len(minDistanceCutting) < lenCuttingList:

        lastDistance = None
        for n in cuttingList:

            nextPointCutting = Point(n.dataval[0].exterior.coords[0])
            distance         = lastPointAdded.distance(nextPointCutting)
            if lastDistance == None or distance < lastDistance:
                nearestPoint = nextPointCutting
                nearestNode  = n
            lastDistance = distance

        lastPointAdded = nearestPoint
        lastNodeAdded  = nearestNode
        minDistanceCutting.append(nearestNode)
        cuttingList.remove(nearestNode)
 

    return minDistanceCutting

#  ============================================================
#  inner functions above, called by functions below


    
def optimize(treeList, treeListPos, treeListNeg, processing_settings_data, masterRoot=None):


    # calls def startAdding two times to find out if pos start or neg start is opt
    # this removes parent child deps
    # nodes in noDepsWithFirstElement are not sorted with greedy at this point
    noDepsWithFirstElement          =   findOutFirstElement(treeListPos, treeListNeg, treeList)


    # if this configuration is set, the roots of a tree are used for cutting
    # sign == None is a condition to identify polygons to cut in def startAddingNodes 
    if processing_settings_data['opt']['out_cut_bb'] == False:
        for tree in treeList:
            tree[0].sign = None

    finalOptList, cutOutList        =   startAddingNodes(noDepsWithFirstElement)
    minCuttingOrderList             =   calcCuttingOrder(finalOptList[-1], cutOutList)

    return finalOptList, minCuttingOrderList


def main(config, path_to_file):


    global processing_settings
    processing_settings            = config.get('processing_settings')
    dataList, motherPoly_z_value   = getData(path_to_file)
    sortedDataList                 = sortData(dataList) 
    nodeList                       = makeNodes(sortedDataList)
    treeList                       = buildTrees(nodeList,motherPoly_z_value)

    # from same data make two other trees, becaus def findOutfirstElement in def optimize
    # uses def startAddingNodes to check is starting with pos sign or with negative sign is optimal
    # the opt algo destroys the child-parent relations, so another call of def startAddingNodes
    # would not work (dependencies are necessary for the algo
    dataList_pos, motherPoly_z_value_pos  = getData(path_to_file)
    sortedDataList_pos                    = sortData(dataList_pos) 
    nodeList_pos                          = makeNodes(sortedDataList_pos)
    treeList_pos                          = buildTrees(nodeList_pos,motherPoly_z_value_pos)

    dataList_neg, motherPoly_z_value_neg  = getData(path_to_file)
    sortedDataList_neg                    = sortData(dataList_neg) 
    nodeList_neg                          = makeNodes(sortedDataList_neg)
    treeList_neg                          = buildTrees(nodeList_neg,motherPoly_z_value_neg)


    if processing_settings['opt']['out_cut_bb']:
        # here the roots of every tree get a sign and a parent -> masterRoot based on motherPoly
        # but it's not appended to treeList
        treeList, masterRoot        = makeMasterRoot(treeList, motherPoly_z_value, processing_settings) 
        optimizedList, minCutting   = optimize(treeList, treeList_pos, treeList_neg, processing_settings, masterRoot)      
    else:
        optimizedList, minCutting   = optimize(treeList, treeList_pos, treeList_neg, processing_settings)


    return optimizedList, minCutting

        
    



    




