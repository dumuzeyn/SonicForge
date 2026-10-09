"""Shared spatial hierarchy and secondary artwork for music-derived covers."""
from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

VERSION = "cover-composition-v3"
ROUND_SAFE_RADIUS = .46
ARTWORK_LIFT = .025
MOTION = {"spiral","orbit","wave","comet","wing","bird","butterfly","ship"}
ANGULAR = {"prism","mirror","claw","lightning","sword","shield","crown","labyrinth","mountain"}


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
    return dict(version=VERSION,language=language,title_zone=zone,
                title_alignment='left',hero_center=center,hero_size=span,
                title_edge='bottom' if calm else 'top',round_safe_radius=ROUND_SAFE_RADIUS,
                artwork_lift=ARTWORK_LIFT)


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
    palette=np.median(pixels.reshape(-1,3),axis=0)
    paper=np.clip(palette*.30+np.array([246,231,203])*.70,0,255).astype(int)
    accent=np.clip(palette*.65+np.array([225,176,128])*.35,0,255).astype(int)
    raster_size=min(4096,size*3)
    primary=Image.new('L',(raster_size,raster_size));secondary=Image.new('L',(raster_size,raster_size))
    d=ImageDraw.Draw(primary);q=ImageDraw.Draw(secondary)
    cx,cy=plan['center'];mass=plan['mass'];rhythm=plan['rhythm']
    energy=np.asarray(plan['energy_profile']);activity=np.asarray(plan['activity_profile'])
    def points(coords):return [(round(a*raster_size),round(b*raster_size)) for a,b in coords]
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
    if scene['language']=='motion':
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
