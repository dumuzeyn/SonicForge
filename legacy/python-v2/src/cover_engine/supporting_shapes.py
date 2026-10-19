"""Sixty named compositions of subordinate, music-shaped artwork."""
import math

import numpy as np
from PIL import Image, ImageDraw

SECONDARY_FAMILIES = {
    'motion': ('broken_orbits','woven_currents','spiral_fan','rising_echoes',
               'braided_rivers','woven_rapids','turbulent_streams','sweeping_tides',
               'drifting_orbits','crescent_fan','ripple_crown','winding_ribbons',
               'comet_trails','wave_bursts','vortex_fragments','pulse_bridges',
               'harmonic_loops','fluid_lattice','twin_rings','swept_contours'),
    'facets': ('plane_field','crystal_fan','fractured_ridges','floating_mosaic',
               'fractured_sunburst','crystal_corners','folded_mesh','crystalline_branches',
               'stepped_shards','fan_planes','tectonic_seams','zigzag_fissures',
               'prismatic_sails','clustered_diamonds','diamond_constellation','shard_bridges',
               'layered_plates','polygon_petals','folded_rosette','cut_ribbons'),
    'organic': ('petal_stream','contour_garden','floating_seeds','branching_canopy',
                'leaf_clusters','radial_fronds','leaf_constellation','leaf_crown',
                'dune_contours','branching_roots','wave_contours','shell_ridges',
                'bloom_clusters','soft_roses','floating_pollen','petal_echoes',
                'twisted_vines','coral_threads','droplet_branches','silken_leaves'),
}


def advanced_support(size, plan, scene):
    primary = Image.new('L', (size, size));secondary = Image.new('L', (size, size))
    draws = (ImageDraw.Draw(primary), ImageDraw.Draw(secondary))
    language = scene['language'];variant = scene['secondary_variant'] - 4
    group, arrangement = divmod(variant, 4)
    rng = np.random.default_rng(plan.get('layout_seed', 0))
    phase = scene['secondary_phase'] + arrangement * .35
    energy = np.asarray(plan['energy_profile']);activity = np.asarray(plan['activity_profile'])
    mass, rhythm, flow = plan['mass'], plan['rhythm'], plan['flow']
    cx, cy = plan['center']
    items = []
    count = 4 + arrangement + round(rhythm * 3)
    def points(coords):
        dx,dy=scene.get('secondary_offset',(0,0))
        stretch=scene.get('secondary_stretch',(1,1))
        return [(round((cx+(x-cx)*stretch[0]+dx)*size),
                 round((cy+(y-cy)*stretch[1]+dy)*size)) for x,y in coords]
    def path(coords, widths, index=0, alpha=220):
        coords=np.asarray(coords,dtype=float);tangent=np.gradient(coords,axis=0)
        normal=np.column_stack((-tangent[:,1],tangent[:,0]))
        normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-8)
        normal*=np.broadcast_to(np.asarray(widths),len(coords))[:,None]/2
        draws[index%2].polygon(points(np.concatenate((coords+normal,(coords-normal)[::-1]))),fill=alpha)
    def polygon(coords, index=0):
        draws[index%2].polygon(points(coords),fill=230)
    def profile(t, values=energy):
        return np.interp(t,np.linspace(0,1,len(values)),values)
    def register(x,y):
        items.append((scene['secondary_family'],float(x),float(y)))
    if language == 'motion':
        for band in range(count):
            t=np.linspace(0,1,160)
            angle=phase+band*.37+t*math.pi*(1.2+arrangement*.24)
            envelope=profile(t)
            if group==0:
                x=.03+.94*t
                y=cy+(.16+band*.035)*np.sin(t*math.pi*(1.1+arrangement*.4)+phase+band*.2)
                y+=(envelope-.5)*.08+np.sin(t*math.pi*4+band)*.025
            elif group==1:
                radius=.22+t*(.12+arrangement*.035)+band*.016
                x=cx+radius*np.cos(angle);y=cy+radius*(.62+flow*.2)*np.sin(angle)
                if arrangement==1:
                    angle=phase+band*math.tau/count+t*math.pi*.65
                    radius=.28+.06*np.sin(t*math.pi)
                    x=cx+radius*np.cos(angle);y=cy+radius*.8*np.sin(angle)
                elif arrangement==2:
                    angle=phase+band*math.tau/count+(t-.5)*.4
                    radius=.23+t*.21
                    x=cx+radius*np.cos(angle);y=cy+radius*.8*np.sin(angle)
                elif arrangement==3:
                    x=.03+t*.94
                    y=cy+.26*np.sin(t*math.pi*2+band*.4+phase)
                if band%2==0:
                    segment=slice(18+arrangement*4,145-arrangement*5)
                    x=x[segment];y=y[segment];envelope=envelope[segment];t=t[segment]
            elif group==2:
                angle=phase+band*math.tau/count
                radius=.23+.10*t
                x=cx+radius*np.cos(angle+t*(.28+arrangement*.2))
                y=cy+radius*.8*np.sin(angle+t*(.28+arrangement*.2))
                x+=.035*np.sin(t*math.pi*2+phase)
                y+=.024*np.sin(t*math.pi*(2+arrangement))
            else:
                angle=t*math.tau+band*.16+phase
                ripple=.025*np.sin(angle*(2+arrangement)+band)
                radius=.28+band*.02+ripple
                x=cx+radius*np.cos(angle)
                y=cy+radius*.7*np.sin(angle)+.025*np.sin(angle*(3+arrangement))
                if arrangement==2:
                    x+=(.08 if band%2 else -.08)
                    y+=.06*np.sin(angle)
                elif arrangement==3:
                    x=.05+t*.9
                    y=cy+.18*np.sin(t*math.pi+phase)+band*.025
            widths=(.005+.014*mass)*(.55+envelope)*(.50+.5*np.sin(t*math.pi)**.6)
            path(np.column_stack((x,y)),widths,band)
            register(x[-1],y[-1])
    elif language == 'facets':
        for item in range(count+2):
            t=item/max(1,count+1);angle=phase+t*math.tau
            length=.04+.08*energy[item%12]+arrangement*.008
            width=.015+.028*activity[item%12]
            if group==0:
                c=np.array([cx+(.34+.02*(item%3))*math.cos(angle),cy+.28*math.sin(angle)])
                direction=angle+arrangement*.18
                if arrangement==1:
                    c=np.array([.16+.68*(item%2),.16+.64*t])
                    direction=(-1 if item%2 else 1)*.7
                elif arrangement==2:
                    c=np.array([.09+t*.83,cy+.20+.06*np.sin(item*math.pi/2)])
                    direction=.2+item*.43
                elif arrangement==3:
                    c=np.array([cx+.33*math.cos(angle),cy+.30*math.sin(angle)])
                    direction=angle
                    path(np.array([c,c-np.array([math.cos(angle),math.sin(angle)])*.10]),.005,item)
            elif group==1:
                c=np.array([.08+t*.84,cy+.27+.06*math.sin(t*math.pi*(2+arrangement)+phase)])
                direction=(-1 if item%2 else 1)*(.5+arrangement*.12)
            elif group==2:
                c=np.array([cx+.37*math.cos(angle),cy+.30*math.sin(angle)])
                c+=rng.uniform(-.025,.025,2);direction=angle+math.pi/4
                length*=.8+arrangement*.16
                if arrangement==1:
                    c=np.array([.15+.70*(item%2)+rng.uniform(-.05,.05),.24+t*.53])
                elif arrangement==3:
                    c=np.array([.08+t*.85,cy+.28+.045*np.sin(t*math.pi*2+phase)])
            else:
                c=np.array([.08+t*.85,cy+.25+.04*np.sin(t*math.pi*2+phase)])
                direction=.15+arrangement*.18
                if arrangement==1:
                    c=np.array([cx+.35*math.cos(angle),cy+.29*math.sin(angle)])
                    direction=angle+.3
                elif arrangement==2:
                    c=np.array([cx+.30*math.cos(angle),cy+.28*math.sin(angle)])
                    direction=angle
            u=np.array([math.cos(direction),math.sin(direction)]);v=np.array([-u[1],u[0]])
            if group==2:
                coords=(c-u*length,c-v*width,c+u*length,c+v*width)
            elif group==3:
                coords=(c-u*length-v*width,c+u*length*.8-v*width*.3,
                        c+u*length+v*width*.4,c-u*length*.5+v*width)
            else:
                coords=(c-u*length,c+u*length*.65-v*width,c+u*length*.4+v*width)
            polygon(coords,item);register(*c)
        if group in (1,3):
            for band in range(2+arrangement%2):
                t=np.linspace(0,1,12)
                coords=np.column_stack((.06+t*.88,cy+.21+band*.045+(energy-.5)*(.06+arrangement*.02)))
                path(coords,.004+.002*arrangement,band)
    else:
        for item in range(count+2):
            t=item/max(1,count+1);angle=phase+t*math.tau
            cx0=cx+.37*math.cos(angle);cy0=cy+.29*math.sin(angle)
            radius=.02+.038*energy[item%12]
            a=np.linspace(0,math.tau,100)
            if group==0:
                # Paired leaves, increasingly spaced and elongated across arrangements.
                for side in (-1,1):
                    xx=cx0+radius*(1.2+arrangement*.3)*np.cos(a)
                    yy=cy0+radius*.60*np.sin(a)+side*.011
                    rotation=angle+side*.22
                    dx=xx-cx0;dy=yy-cy0
                    if arrangement==1:
                        dx*=.6;dy*=2.8
                    elif arrangement==2:
                        cx0+=rng.uniform(-.055,.055);cy0+=rng.uniform(-.03,.03)
                    elif arrangement==3:
                        cx0=cx+.37*math.cos(phase+t*math.pi)
                        cy0=cy+.30*math.sin(phase+t*math.pi)
                    coords=np.column_stack((cx0+dx*np.cos(rotation)-dy*np.sin(rotation),
                                             cy0+dx*np.sin(rotation)+dy*np.cos(rotation)))
                    polygon(coords,item+(side>0))
            elif group==1:
                t0=np.linspace(0,1,120)
                xx=.04+t0*.92
                yy=cy+.21+item*.016+.04*np.sin(t0*math.pi*(1.2+arrangement*.4)+phase)
                if scene['title_edge']=='bottom':yy=cy-.24-item*.016+.04*np.sin(t0*math.pi*1.7+phase)
                if arrangement==1:
                    xx=.09+t0*.82
                    yy=cy+.24-.18*t0+item*.018+.04*np.sin(t0*math.pi*3+phase)
                elif arrangement==2:
                    xx=.05+t0*.9
                    yy=cy+.18*np.sin(t0*math.pi*2+phase)+item*.016
                elif arrangement==3:
                    a0=t0*math.pi*1.15+phase
                    xx=cx+(.29+item*.017)*np.cos(a0)
                    yy=cy+(.23+item*.015)*np.sin(a0)
                widths=(.004+.005*mass)*(.50+profile(t0))
                path(np.column_stack((xx,yy)),widths,item)
                cx0,cy0=xx[-1],yy[-1]
            elif group==2:
                petals=3+arrangement
                r=radius*(1+.22*np.sin(a*petals+phase))
                coords=np.column_stack((cx0+r*np.cos(a),cy0+r*np.sin(a)))
                path(coords,.004+.004*mass,item)
                if arrangement%2:
                    polygon(np.column_stack((cx0+r*.4*np.cos(a),cy0+r*.4*np.sin(a))),item+1)
            else:
                t0=np.linspace(0,1,80)
                xx=cx0+t0*.07
                yy=cy0+.05*np.sin(t0*math.pi*(1.1+arrangement*.2)+angle)
                if arrangement==1:
                    xx=cx0+.02*np.sin(t0*math.pi*2)
                    yy=cy0+t0*.09
                elif arrangement==2:
                    xx=cx0+t0*.06
                    yy=cy0+.06*np.sin(t0*math.pi)
                elif arrangement==3:
                    xx=cx0+.07*np.sin(t0*math.pi)
                    yy=cy0+t0*.07
                width=(.005+.013*mass)*np.sin(t0*math.pi)**.7
                path(np.column_stack((xx,yy)),width,item)
                for branch in (24,50):
                    xx0,yy0=xx[branch],yy[branch]
                    twig=np.column_stack((xx0+t0*.026,yy0-t0*.025*np.sin(angle+arrangement)))
                    path(twig,width*.6,item+1)
            register(cx0,cy0)
    return primary,secondary,items
