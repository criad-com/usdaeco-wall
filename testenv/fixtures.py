"""Independent synthetic IFC wall fixture, including a cut and filling."""
import ifcopenshell
from ifcopenshell.api import run
import ifcopenshell.util.element as element
import ifcopenshell.util.unit as unit
import numpy as np


def build_baseline(output, millimetres=False):
    model=ifcopenshell.file(schema='IFC4X3')
    project=run('root.create_entity',model,ifc_class='IfcProject',name='Wall fixture')
    run('unit.assign_unit',model,length={'is_metric':True,'raw':'MILLIMETERS' if millimetres else 'METERS'})
    scale=unit.calculate_unit_scale(model)
    context=run('context.add_context',model,context_type='Model')
    body=run('context.add_context',model,context_type='Model',context_identifier='Body',target_view='MODEL_VIEW',parent=context)
    axis=run('context.add_context',model,context_type='Model',context_identifier='Axis',target_view='GRAPH_VIEW',parent=context)
    facility=run('root.create_entity',model,ifc_class='IfcBuilding',name='Facility')
    level=run('root.create_entity',model,ifc_class='IfcBuildingStorey',name='Level')
    run('aggregate.assign_object',model,relating_object=project,products=[facility])
    run('aggregate.assign_object',model,relating_object=facility,products=[level])
    typ=run('root.create_entity',model,ifc_class='IfcWallType',name='Layered wall',predefined_type='STANDARD')
    matset=run('material.add_material_set',model,name='Layered section',set_type='IfcMaterialLayerSet')
    for name,width,category,priority in [('Plaster',.02,'finish',10),('Masonry',.16,'structure',50),('Plaster',.02,'finish',10)]:
        mat=run('material.add_material',model,name=name)
        layer=run('material.add_layer',model,layer_set=matset,material=mat)
        layer.LayerThickness=width/scale; layer.Category=category; layer.Priority=priority
    run('material.assign_material',model,products=[typ],type='IfcMaterialLayerSet',material=matset)
    walls=[]
    for i in range(2):
        wall=run('root.create_entity',model,ifc_class='IfcWall',name='Wall '+str(i))
        run('type.assign_type',model,related_objects=[wall],relating_type=typ)
        run('spatial.assign_container',model,relating_structure=level,products=[wall])
        matrix=np.eye(4)
        if i:
            matrix[:3,0]=(0,1,0); matrix[:3,1]=(-1,0,0); matrix[:3,3]=(4,0,0)
        run('geometry.edit_object_placement',model,product=wall,matrix=matrix)
        usage=element.get_material(wall)
        usage.OffsetFromReferenceLine=0
        rep=run('geometry.add_wall_representation',model,context=body,length=4 if not i else 3,height=3,thickness=.2)
        run('geometry.assign_representation',model,product=wall,representation=rep)
        rep=run('geometry.add_axis_representation',model,context=axis,axis=[(0.,0.),(4. if not i else 3.,0.)])
        run('geometry.assign_representation',model,product=wall,representation=rep)
        pset=run('pset.add_pset',model,product=wall,name='Pset_WallCommon')
        run('pset.edit_pset',model,pset=pset,properties={'IsExternal':True,'LoadBearing':True,'Reference':'Retain this field'})
        qto=run('pset.add_qto',model,product=wall,name='Qto_WallBaseQuantities')
        run('pset.edit_qto',model,qto=qto,properties={'GrossSideArea':12. if not i else 9.,'NetSideArea':10.11 if not i else 9.,'GrossVolume':2.4 if not i else 1.8,'NetVolume':2.022 if not i else 1.8})
        walls.append(wall)
    run('geometry.connect_path',model,relating_element=walls[0],related_element=walls[1],relating_connection='ATEND',related_connection='ATSTART')
    opening=run('root.create_entity',model,ifc_class='IfcOpeningElement',name='Opening')
    rep=run('geometry.add_wall_representation',model,context=body,length=.9,height=2.1,thickness=.4)
    run('geometry.assign_representation',model,product=opening,representation=rep)
    run('feature.add_feature',model,feature=opening,element=walls[0])
    matrix=np.eye(4); matrix[:3,3]=(.55,-.1,0)
    run('geometry.edit_object_placement',model,product=opening,matrix=matrix)
    door=run('root.create_entity',model,ifc_class='IfcDoor',name='Door')
    door.OverallWidth=.9/scale; door.OverallHeight=2.1/scale
    run('spatial.assign_container',model,products=[door],relating_structure=level)
    run('geometry.edit_object_placement',model,product=door,matrix=matrix)
    run('feature.add_filling',model,opening=opening,element=door)
    model.write(str(output))
