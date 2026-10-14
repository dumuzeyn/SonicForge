"""Shared spatial hierarchy and secondary artwork for music-derived covers."""
from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .supporting_shapes import SECONDARY_FAMILIES, advanced_support

VERSION = "cover-composition-v4"
ROUND_SAFE_RADIUS = .46
ARTWORK_LIFT = .025
MOTION = {"spiral","orbit","wave","comet","wing","bird","butterfly","ship","swan","fish","jellyfish","atom","helix","rainbow"}
ANGULAR = {"prism","mirror","claw","lightning","sword","shield","crown","labyrinth","mountain","arrow","diamond","hexagon","antenna","pyramid","tower","chain","book","scales"}


def spatial_plan(plan, title, show_title=True):
    """Reserve type space before placing the hero, using one shared axis."""
    calm=plan['flow']>.64 and plan['mass']<.28
    header_height=.20 if len(title)<19 else .27 if len(title)<34 else .34
    # The whole title/artist rectangle fits inside a disc with a 4% radial
    # inset. Players may crop the square cover to a circle without losing ink.
    top=.14
    bottom=top+header_height
    half_width=math.sqrt(ROUND_SAFE_RADIUS**2-max(abs(top-.5),abs(bottom-.5))**2)
    left,right=.5-half_width,.5+half_width
    if not show_title:
        zone=None;center=(.54,.48)
    elif calm:
        zone=(left,1-bottom,right,1-top)
        center=(.45,min(.43,zone[1]-.045-(.44+.08*plan['mass'])/2))
    else:
        zone=(left,top,right,bottom)
        center=(.57,max(.54,zone[3]+.035+(.44+.08*plan['mass'])*.47))
    span=.44+.08*plan['mass']
    if header_height>.25 and show_title:
        span*=.90
        if not calm:
            center=(.57,min(.66,zone[3]+.035+span*.47))
    center=(center[0],center[1]-ARTWORK_LIFT)
    language='motion' if plan['motif'] in MOTION else 'facets' if plan['motif'] in ANGULAR else 'organic'
    rng = np.random.default_rng(plan.get('layout_seed', 0))
    variant = (int(rng.integers(20)) + round(plan['dynamic'] * 3 + plan['rhythm'] * 2)) % 20
    return dict(version=VERSION,language=language,title_zone=zone,
                title_alignment='left',hero_center=center,hero_size=span,
                title_edge='bottom' if calm else 'top',round_safe_radius=ROUND_SAFE_RADIUS,
                artwork_lift=ARTWORK_LIFT, secondary_variant=variant,
                secondary_family=SECONDARY_FAMILIES[language][variant],
                secondary_phase=float(rng.uniform(-.8, .8)),
                secondary_spacing=float(rng.uniform(.82, 1.18)),
                title_density=min(1,len(title)/44))


def supporting_artwork(image, plan, scene, protected_boxes=()):
    """Layer subordinate gestures and accents around, not over, the hero/type."""
    size=min(1536,min(image.size));scale=size/min(image.size)
    canvas=image.convert('RGB').resize((size,size),Image.Resampling.LANCZOS)
    pixels=np.asarray(canvas,dtype=float)
    y,x=np.mgrid[0:size,0:size].astype(float)/size
    zone=scene['title_zone']
    # A broad tonal field creates a quiet type area instead of a separate card.
    if zone:
        distance=y if scene['title_edge']=='top' else 1-y
        field=.22*np.exp(-((distance-.09)/.19)**2)
        pixels*=1-field[...,None]
        canvas=Image.fromarray(np.clip(pixels,0,255).astype(np.uint8))
    from .materials import cover_material
    material = plan.get('material_palette') or cover_material(image)
    paper = plan.get('material_color',material['light_ink'])
    accent = tuple(round(v) for v in (np.asarray(paper)*.72+np.asarray(material['source_color'])*.28))
    raster_size=min(4096,size*3)
    primary=Image.new('L',(raster_size,raster_size));secondary=Image.new('L',(raster_size,raster_size))
    d=ImageDraw.Draw(primary);q=ImageDraw.Draw(secondary)
    cx,cy=plan['center'];mass=plan['mass'];rhythm=plan['rhythm']
    energy=np.asarray(plan['energy_profile']);activity=np.asarray(plan['activity_profile'])
    # Adapt the secondary field to silhouette proportions and title occupancy.
    # Leave the protected type/hero areas to the exact clearance gate below.
    gray=np.asarray(canvas.convert('L'),dtype=np.float32)/255
    blur=np.asarray(canvas.convert('L').filter(ImageFilter.GaussianBlur(max(1,size*.035))),dtype=np.float32)/255
    complexity=np.clip(np.abs(gray-blur)*5,0,1)
    left_busy=float(complexity[:,:size//3].mean());right_busy=float(complexity[:,size*2//3:].mean())
    offset=(float(np.clip((left_busy-right_busy)*.20,-.045,.045)),
            -.015 if scene.get('title_edge')=='bottom' else .015)
    aspect=float(scene.get('silhouette_aspect',1))
    density=float(scene.get('title_density',0))
    stretch=(float(np.clip(.94+aspect*.055,.91,1.07)),.94-density*.035)
    scene.update(secondary_offset=offset,secondary_stretch=stretch,
                 adaptation='palette / local contrast / silhouette proportions / title clearance')
    def points(coords):
        return [(round((cx+(a-cx)*stretch[0]+offset[0])*raster_size),
                 round((cy+(b-cy)*stretch[1]+offset[1])*raster_size)) for a,b in coords]
    def stroke(draw,coords,width,alpha=255):
        draw.line(points(coords),fill=alpha,width=max(1,round(width*raster_size)),joint='curve')
    def ribbon(draw,coords,widths,alpha=255):
        coords=np.asarray(coords);tangent=np.gradient(coords,axis=0)
        normals=np.column_stack((-tangent[:,1],tangent[:,0]))
        normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-8)
        normals*=np.asarray(widths)[:,None]/2
        outline=np.concatenate((coords+normals,(coords-normals)[::-1]))
        draw.polygon(points(outline),fill=alpha)
    count=3+round(rhythm*5)
    items=[]
    variant=scene.get('secondary_variant',0)
    phase=scene.get('secondary_phase',0)
    rng=np.random.default_rng(plan.get('layout_seed',0))
    if variant >= 4:
        primary,secondary,items = advanced_support(raster_size,plan,scene)
    elif variant:
        def profile(t, values=energy):
            return np.interp(t,np.linspace(0,1,len(values)),values)
        if scene['language']=='motion':
            for band in range(3+round(plan['dynamic']*2)):
                t=np.linspace(0,1,160)
                if variant==1:
                    xx=.04+.93*t
                    yy=cy+(.23+.045*band)*np.sin(t*math.pi*1.2+phase)+.045*np.sin(t*math.pi*4+band)
                elif variant==2:
                    angle=t*math.pi*(.85+.5*plan['flow'])+phase+band*.27
                    radius=.23+t*.26+band*.018
                    xx=cx+radius*np.cos(angle)
                    yy=cy+radius*.76*np.sin(angle)
                else:
                    xx=.10+.85*t
                    yy=.20+band*.135+.16*t+.065*np.sin(t*math.pi*(1.3+rhythm)+phase+band)
                coords=np.column_stack((xx,yy))
                widths=(.009+.010*mass)*(.55+.75*profile(t))*(1-band*.09)
                ribbon(d if band%2 else q,coords,widths,220)
                items.append((scene['secondary_family'],float(xx[-1]),float(yy[-1])))
            for i in range(count):
                angle=phase+i*math.pi*2/count
                xx=cx+.37*math.cos(angle);yy=cy+.30*math.sin(angle)
                a=np.linspace(angle-.20,angle+.20,40)
                coords=np.column_stack((xx+.05*np.cos(a),yy+.05*np.sin(a)))
                stroke(d,coords,.004+.005*rhythm)
                items.append(('curved_echo',xx,yy))
        elif scene['language']=='facets':
            for i in range(count+3):
                angle=phase+.25+i*math.pi*1.6/(count+2)
                if variant==1:
                    center=np.array([cx+.38*math.cos(angle),cy+.32*math.sin(angle)])
                    direction=angle+phase*.3
                    length=.06+.10*activity[i%12]
                elif variant==2:
                    center=np.array([.10+i*.78/(count+2),cy+.27+.05*np.sin(i+phase)])
                    direction=-.5+energy[i%12]*1.2
                    length=.065+.07*plan['dynamic']
                else:
                    center=np.array([cx+.40*math.cos(angle),cy+.33*math.sin(angle)])
                    center+=rng.uniform(-.035,.035,2)
                    direction=angle+.7
                    length=.035+.065*energy[i%12]
                u=np.array([math.cos(direction),math.sin(direction)])
                v=np.array([-u[1],u[0]])
                width=.018+.026*activity[i%12]
                vertices=[center-u*length,center-v*width-u*length*.25,
                          center+u*length*.8,center+v*width]
                (d if i%2 else q).polygon(points(vertices),fill=230)
                items.append((scene['secondary_family'],*center))
            if variant==2:
                for band in range(2):
                    t=np.linspace(0,1,12)
                    coords=np.column_stack((.06+t*.88,cy+.28+band*.04+(energy-.5)*.10))
                    stroke(q,coords,.006)
        else:
            if variant==1:
                for band in range(4):
                    t=np.linspace(0,1,180)
                    xx=.04+.92*t
                    yy=cy+.20+band*.033+.06*np.sin(t*math.pi*(1.5+plan['flow'])+phase)
                    if scene['title_edge']=='bottom':yy=cy-.22-band*.033+.06*np.sin(t*math.pi*1.6+phase)
                    ribbon(q if band%2 else d,np.column_stack((xx,yy)),
                           (.005+.006*mass)*(.7+profile(t)),210)
                    items.append(('contour',float(xx[-1]),float(yy[-1])))
            elif variant==2:
                for i in range(count+4):
                    angle=phase+i*math.pi*2/(count+4)
                    xx=cx+.39*math.cos(angle);yy=cy+.29*math.sin(angle)
                    radius=.016+.026*energy[i%12]
                    a=np.linspace(0,math.pi*2,60)
                    coords=np.column_stack((xx+radius*np.cos(a),yy+radius*.58*np.sin(a)))
                    ribbon(q if i%2 else d,coords,np.full(len(a),.006+.006*mass),225)
                    items.append(('seed_ripple',xx,yy))
            else:
                for branch in range(3):
                    t=np.linspace(0,1,140)
                    xx=.08+.85*t
                    yy=cy+.23+.035*branch-.10*np.sin(t*math.pi+phase)-t*.035
                    if scene['title_edge']=='bottom':yy=cy-.25-.035*branch+.08*np.sin(t*math.pi+phase)
                    coords=np.column_stack((xx,yy))
                    ribbon(q,coords,(.005+.008*mass)*(.6+profile(t)),225)
                    for i in range(count):
                        index=round((.10+i*.78/max(1,count-1))*(len(t)-1))
                        xx0,yy0=coords[index];sign=1 if scene['title_edge']=='bottom' else -1
                        tt=np.linspace(0,1,40)
                        twig=np.column_stack((xx0+tt*.06,yy0+sign*(.035+.055*activity[i%12])*np.sin(tt*math.pi/2)))
                        ribbon(d,twig,(.006+.009*mass)*np.sin(tt*math.pi),220)
                        items.append(('canopy_leaf',xx0,yy0))
    elif scene['language']=='motion':
        # Sweeps carry the rotational gesture into the lower/outer space.
        for band in range(2):
            angles=np.linspace(.04*math.pi,(1.48+.08*plan['dynamic'])*math.pi,200)
            rx=.41+.09*band;ry=.30+.045*band
            coords=np.column_stack((cx+rx*np.cos(angles),cy+ry*np.sin(angles)))
            envelope=np.interp(np.linspace(0,1,len(coords)),np.linspace(0,1,12),energy)
            widths=(.007+.017*mass)*(1-.48*band)*(.55+.6*envelope)
            ribbon(q if band==0 else d,coords,widths,210 if band==0 else 180)
        for i in range(count):
            a=.22*math.pi+i*.68*math.pi/max(1,count-1)
            r=.36+.04*activity[min(11,i*2)]
            px,py=cx+.40*math.cos(a),cy+r*math.sin(a)
            length=.045+.035*energy[min(11,i*2)]
            if i%2==0:
                # A tapered orbital fragment is a secondary shape in its own
                # right, rather than a tiny decorative tick on a generic ring.
                half=.10+.15*energy[min(11,i*2)]
                angles=np.linspace(a-half,a+half,40)
                radius=.035+.015*mass
                outer=np.column_stack((cx+(.40+radius)*np.cos(angles),cy+(r+radius)*np.sin(angles)))
                taper=np.sin(np.linspace(0,math.pi,40))**.8
                inner=np.column_stack((cx+(.40+radius-radius*taper)*np.cos(angles),cy+(r+radius-radius*taper)*np.sin(angles)))
                d.polygon(points(np.concatenate((outer,inner[::-1]))),fill=255)
                items.append(('orbital_fragment',px,py))
            else:
                delta=.15+.10*rhythm
                angles=np.linspace(a-delta,a+delta,24)
                coords=np.column_stack((px+length*np.cos(angles),py+length*np.sin(angles)))
                stroke(d,coords,.003+.005*mass)
                items.append(('rhythm_arc',px,py))
    elif scene['language']=='facets':
        # A directional field of planes echoes edges of the focal sculpture.
        for i in range(count):
            a=.15*math.pi+i*.83*math.pi/max(1,count-1)
            px,py=cx+.38*math.cos(a),cy+.32*math.sin(a)
            length=.055+.09*energy[min(11,i*2)]
            width=.014+.030*activity[min(11,i*2)]
            direction=a+.55+plan['gesture_angle']/80
            u=np.array([math.cos(direction),math.sin(direction)])
            v=np.array([-u[1],u[0]])
            c=np.array([px,py])
            vertices=[c-u*length,c+u*length*.70-v*width,c+u*length,c-u*length*.35+v*width]
            (d if i%2 else q).polygon(points(vertices),fill=220)
            items.append(('plane',px,py))
        lift=scene['artwork_lift']
        coords=((.08,.68-lift),(.21,.82-lift),(.76,.87-lift),(.96,.58-lift))
        stroke(q,coords,.0025,180)
    else:
        # Organic branches create a flowing counterweight to the main emblem.
        t=np.linspace(0,1,160)
        horizontal=.06+.91*t
        vertical=cy+.25+.075*np.sin(t*math.pi)-.10*t
        coords=np.column_stack((horizontal,vertical))
        if scene['title_edge']=='bottom':coords[:,1]=cy-.22-.10*np.sin(t*math.pi)+.09*t
        widths=(.004+.012*mass)*(.45+.55*np.interp(t,np.linspace(0,1,12),energy))
        ribbon(q,coords,widths,220)
        for i in range(count):
            t0=.14+i*.72/max(1,count-1);index=round(t0*(len(coords)-1))
            px,py=coords[index];direction=1 if scene['title_edge']=='bottom' else -1
            length=.045+.06*activity[min(11,i*2)]
            tip=np.array([px+.055,py+direction*length])
            base=np.array([px,py])
            tt=np.linspace(0,1,32)[:,None]
            def curve(a,b,c,e):return (1-tt)**3*a+3*(1-tt)**2*tt*b+3*(1-tt)*tt**2*c+tt**3*e
            outward=curve(base,np.array([px-.025,py+direction*length*.65]),
                          tip-np.array([.020,direction*length*.15]),tip)
            inward=curve(tip,tip+np.array([.018,-direction*length*.45]),
                         np.array([px+.022,py+direction*length*.05]),base)
            d.polygon(points(np.concatenate((outward,inward))),fill=220)
            items.append(('petal',px,py))
    # Keep the title's breathing room and the hero's silhouette genuinely clear.
    gate=np.ones((size,size),dtype=float)
    if zone:
        if scene['title_edge']=='top':gate*=np.clip((y-zone[3])/.045,0,1)
        else:gate*=np.clip((zone[1]-y)/.045,0,1)
    hero=plan['bounds'];hx0,hy0,hx1,hy1=(v*scale for v in hero)
    keepout=Image.new('L',(size,size));kd=ImageDraw.Draw(keepout)
    pad=round(size*.017)
    kd.rounded_rectangle((hx0-pad,hy0-pad,hx1+pad,hy1+pad),radius=pad,fill=255)
    for box in protected_boxes:
        kd.rectangle(tuple(v*scale for v in box),fill=255)
    keepout=keepout.filter(ImageFilter.GaussianBlur(max(1,size*.017)))
    gate*=1-np.asarray(keepout,dtype=float)/255
    for mask,color,opacity in ((secondary,accent,.58),(primary,paper,.64)):
        mask=mask.resize((size,size),Image.Resampling.LANCZOS)
        mask=Image.fromarray(np.clip(np.asarray(mask)*gate*opacity,0,255).astype(np.uint8))
        # A narrowly bounded tint under low-contrast strokes makes every scheme
        # readable over both light and dark folds without repainting the cover.
        from .materials import backing_for_ink
        from .music_lettering import luminance
        color_level=float(luminance(color))
        background_level=luminance(np.asarray(canvas.convert('RGB')))
        ratio=(np.maximum(color_level,background_level)+.05)/(np.minimum(color_level,background_level)+.05)
        insufficient=np.clip((2.7-ratio)/1.7,0,1)
        footprint=mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(max(.6,size*.002)))
        alpha=np.asarray(footprint,dtype=np.float32)*insufficient*.40
        backing=Image.new('RGBA',canvas.size,(*backing_for_ink(material,color),0))
        backing.putalpha(Image.fromarray(np.uint8(np.clip(alpha,0,255))))
        canvas=Image.alpha_composite(canvas.convert('RGBA'),backing)
        layer=Image.new('RGBA',(size,size),tuple(int(v) for v in color)+(0,));layer.putalpha(mask)
        canvas=Image.alpha_composite(canvas.convert('RGBA'),layer)
    scene.update(secondary_elements=items,secondary_count=len(items)+2,
                 title_zone_pixels=tuple(round(v*min(image.size)) for v in zone) if zone else None,
                 hero_bounds=plan['bounds'],hierarchy='title / focal symbol / rhythmic secondary forms')
    result=canvas.convert('RGB').resize(image.size,Image.Resampling.LANCZOS)
    for box in protected_boxes:
        bounds=tuple(round(v) for v in box)
        result.paste(image.crop(bounds),bounds[:2])
    return result,scene
