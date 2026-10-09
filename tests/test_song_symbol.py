import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageChops, ImageFilter

import music2picture
from cover_engine.music_lettering import intersection_fraction
from cover_engine.song_symbol import ABSTRACT_MOTIFS, AUDIO_ARCHETYPES, IMAGERY, _mask, _minimum_filter, compose_song_symbol, symbol_plan
from music2picture_v2.audio_analysis import analyze_audio_array
from music2picture_v2.models import AnalysisBundle
from music2picture_v2.semantics import build_visual_dna
from music2picture_v2.visual_plan import build_visual_plan


class SongSymbolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = analyze_audio_array(np.zeros(22050,dtype=np.float32))
        cls.dna = build_visual_dna(cls.analysis)

    def test_images_match_semantic_cues_without_genre_lookup(self):
        for title,motif in (("Fallen Down","feather"),("Another Love","heart"),
                            ("Animal I Have Become","claw"),("Android Dubstep","prism"),
                            ("Я тебе не верю","mirror"),("Interstellar","star"),("Fire","flame")):
            with self.subTest(title=title):
                self.assertEqual(symbol_plan(self.dna,title)["motif"],motif)
        self.assertEqual(symbol_plan(self.dna,"Untitled","И сердце снова любит")["motif"],"heart")
        self.assertEqual(symbol_plan(self.dna,"Shadow")["source"],"audio")  # No false 'down' match.

    def test_large_contour_erosion_matches_pillow_including_frame_edges(self):
        pixels=np.random.default_rng(17).integers(0,256,(51,67),dtype=np.uint8)
        pixels[:18,:19]=255
        mask=Image.fromarray(pixels)
        for diameter in (3,9,15,31):
            with self.subTest(diameter=diameter):
                expected=mask.filter(ImageFilter.MinFilter(diameter))
                self.assertIsNone(ImageChops.difference(expected,_minimum_filter(mask,diameter)).getbbox())

    def test_forty_families_need_meaning_while_audio_fallback_stays_abstract(self):
        self.assertEqual(len(AUDIO_ARCHETYPES),40)
        self.assertEqual({name for name,_ in IMAGERY},set(AUDIO_ARCHETYPES))
        # Exercise the nearest-shape decision at every archetype, including
        # the newly added forms, rather than just asserting a catalog count.
        from types import SimpleNamespace
        for name,vector in AUDIO_ARCHETYPES.items():
            a,m,o,v,r,t=vector
            design=SimpleNamespace(angularity=a,mass=m,openness=o)
            dna=replace(self.dna,valence=v,rhythmic_density=r,tension=t)
            with patch('cover_engine.song_symbol.design_from_music',return_value=design):
                title=next(cues[0] for motif,cues in IMAGERY if motif==name)
                self.assertEqual(symbol_plan(dna,title)["motif"],name)
                self.assertEqual(symbol_plan(dna,name)["motif"],name)
                fallback=symbol_plan(dna,"Untitled")
                self.assertIn(fallback['motif'],ABSTRACT_MOTIFS)
                if name in ABSTRACT_MOTIFS:
                    self.assertEqual(fallback['motif'],name)

    def test_motion_words_are_understood_without_nautical_invention(self):
        for title in ('КРУЖИТ','Кружится','Крутится','Spin','Spinning'):
            plan=symbol_plan(self.dna,title)
            self.assertEqual(plan['motif'],'spiral')
            self.assertEqual(plan['semantic_source'],'title')
        self.assertEqual(symbol_plan(self.dna,'По кругу')['motif'],'orbit')
        self.assertEqual(symbol_plan(self.dna,'Compasses')['motif'],'compass')
        self.assertEqual(symbol_plan(self.dna,'Glasses')['motif'],'prism')

    def test_all_forty_same_symbols_change_construction_without_size_or_rotation(self):
        soft=replace(self.dna,roughness=.08,arousal=.2,rhythmic_density=.1,attack_strength=.05,
                     crest_factor=.9,bass_mass=.3,absolute_loudness=.3,relaxation=.9,
                     brightness=.15,spectral_flux=.02,tension=.2)
        hard=replace(self.dna,roughness=.7,arousal=.95,rhythmic_density=.9,attack_strength=.9,
                     crest_factor=.1,bass_mass=.9,absolute_loudness=.98,relaxation=.1,
                     brightness=.85,spectral_flux=.4,tension=.8)
        for motif,cues in IMAGERY:
            with self.subTest(motif=motif):
                calm=symbol_plan(soft,cues[0]);powerful=symbol_plan(hard,cues[0])
                self.assertEqual(calm['motif'],powerful['motif'])
                for plan in (calm,powerful):
                    plan.update(aspect=1,gesture_angle=0)
                a=np.asarray(_mask(calm,256))>128;b=np.asarray(_mask(powerful,256))>128
                difference=np.count_nonzero(a^b)/max(1,np.count_nonzero(a|b))
                self.assertGreater(difference,.35)

    def test_measured_song_progression_changes_shape_with_the_same_scalar_features(self):
        first=replace(self.dna,energy_curve=(0.,0.,0.,1.,1.,1.),dynamic_complexity=.9)
        second=replace(first,energy_curve=(1.,1.,1.,0.,0.,0.))
        for title in ('Heart','Feather','Prism','Anchor'):
            a=symbol_plan(first,title);b=symbol_plan(second,title)
            a.update(aspect=1,gesture_angle=0);b.update(aspect=1,gesture_angle=0)
            aa=np.asarray(_mask(a,256))>128;bb=np.asarray(_mask(b,256))>128
            self.assertGreater(np.count_nonzero(aa^bb)/max(1,np.count_nonzero(aa|bb)),.1)

    def test_larger_size_stays_inside_the_canvas_after_rotation(self):
        for motif,cues in IMAGERY:
            plan=symbol_plan(self.dna,cues[0])
            old_size=.32+.065*plan['mass']
            self.assertGreaterEqual(plan['size']/old_size,1.14)
            bounds=_mask(plan,256).getbbox()
            self.assertGreater(min(bounds[:2]),0)
            self.assertLess(max(bounds[2:]),256)

    def test_title_evidence_has_priority_over_lyrics_and_partial_words(self):
        plan=symbol_plan(self.dna,"Ship","love heart love heart fire "*100)
        self.assertEqual(plan['motif'],'ship')
        self.assertEqual(plan['semantic_source'],'title')
        self.assertEqual(symbol_plan(self.dna,"Крылья")['motif'],'wing')
        for title in ('Sunday','Starship','Eyeless','Keyboard','Tearful','Мечта','Лестница',
                      'Частота','Воронеж','Листать','Невероятный'):
            with self.subTest(title=title):
                self.assertEqual(symbol_plan(self.dna,title)['source'],'audio')
        for title,motif in (('Stars','star'),('Butterflies','butterfly'),('Leaves','leaf'),
                            ('Сердцем','heart'),('Деревья','tree'),('Крыльями','wing'),
                            ('Сле\u0308зы','raindrop'),('Полёт','wing')):
            self.assertEqual(symbol_plan(self.dna,title)['motif'],motif)
        self.assertEqual(symbol_plan(self.dna,'Untitled','Дождь и слезы')['semantic_source'],'lyrics')

    def test_ambiguous_title_uses_audio_fit_instead_of_catalog_order(self):
        from types import SimpleNamespace
        for motif in ('moon','flame'):
            a,m,o,v,r,t=AUDIO_ARCHETYPES[motif]
            dna=replace(self.dna,valence=v,rhythmic_density=r,tension=t)
            design=SimpleNamespace(angularity=a,mass=m,openness=o)
            with patch('cover_engine.song_symbol.design_from_music',return_value=design):
                self.assertEqual(symbol_plan(dna,'Moon and Fire')['motif'],motif)
                self.assertEqual(symbol_plan(dna,'Fire and Moon')['motif'],motif)

    def test_symbol_moves_to_quiet_upper_space_and_avoids_protected_objects(self):
        base=Image.new('RGB',(600,600),'#285873')
        _,normal=compose_song_symbol(base,self.dna,'Feather')
        self.assertEqual(normal['placement'],'composed')
        protected=(250,270,350,380)
        _,avoiding=compose_song_symbol(base,self.dna,'Feather',protected_boxes=(protected,))
        self.assertEqual(avoiding['protected_overlap'],0)
        self.assertEqual(intersection_fraction(avoiding['bounds'],protected),0)
        rng=np.random.default_rng(21)
        base.paste(Image.fromarray(rng.integers(0,256,(240,240,3),dtype=np.uint8)),(180,180))
        _,quiet=compose_song_symbol(base,self.dna,'Feather')
        self.assertNotEqual(quiet['center'],normal['center'])

    def test_all_shapes_survive_thumbnail_export_on_light_and_dark_art(self):
        from types import SimpleNamespace
        for name,vector in AUDIO_ARCHETYPES.items():
            a,m,o,v,r,t=vector
            dna=replace(self.dna,valence=v,rhythmic_density=r,tension=t)
            design=SimpleNamespace(angularity=a,mass=m,openness=o)
            for background in ('#172635','#eeeeee','#888888'):
                base=Image.new('RGB',(192,192),background)
                with self.subTest(motif=name,background=background), \
                     patch('cover_engine.song_symbol.design_from_music',return_value=design):
                    title=next(cues[0] for motif,cues in IMAGERY if motif==name)
                    image,plan=compose_song_symbol(base,dna,title)
                    self.assertEqual(plan['motif'],name)
                    self.assertGreaterEqual(plan['contrast_ratio'],3)
                    delta=np.asarray(ImageChops.difference(base,image)).max(axis=2)
                    self.assertGreater(int((delta>30).sum()),40)
                    self.assertEqual(plan['placement'],'composed')
                    self.assertGreaterEqual(plan['composition']['secondary_count'],3)

    def test_banded_art_receives_only_the_contrast_correction_it_needs(self):
        bands=np.zeros((192,192,3),dtype=np.uint8)
        bands[:]=(34,60,73)
        bands[::2]=(201,190,158)
        base=Image.fromarray(bands)
        for title in ('Feather','Heart','Mirror','Snowflake'):
            with self.subTest(title=title):
                image,plan=compose_song_symbol(base,self.dna,title)
                self.assertGreaterEqual(plan['contrast_ratio'],3)
                self.assertGreater(plan['backing_opacity'],0)
                self.assertIsNotNone(plan['composition']['title_zone_pixels'])
        _,quiet=compose_song_symbol(Image.new('RGB',(192,192),'#172635'),self.dna,'Feather')
        self.assertEqual(quiet['backing_opacity'],0)

    def test_new_symbols_match_english_and_russian_titles(self):
        titles={"tree":"Дерево", "leaf":"Осень", "butterfly":"Бабочка", "bird":"Ворон",
                "dragon":"Дракон", "skull":"Череп", "mask":"Маска", "sword":"Клинок",
                "shield":"Щит", "anchor":"Якорь", "compass":"Компас", "ship":"Корабль",
                "planet":"Планета", "comet":"Комета", "spiral":"Спираль", "labyrinth":"Лабиринт",
                "bridge":"Мост", "lantern":"Фонарь", "raindrop":"Дождь", "snowflake":"Снежинка"}
        for motif,ru_title in titles.items():
            english=next(words[0] for name,words in IMAGERY if name==motif)
            with self.subTest(motif=motif):
                self.assertEqual(symbol_plan(self.dna,english)["motif"],motif)
                self.assertEqual(symbol_plan(self.dna,ru_title)["motif"],motif)

    def test_all_silhouettes_are_visible_inside_the_frame_and_reproducible(self):
        base = Image.new("RGB",(384,384),"#285873")
        results=[]
        from types import SimpleNamespace
        for name,vector in AUDIO_ARCHETYPES.items():
            a,m,o,v,r,t=vector
            dna=replace(self.dna,valence=v,rhythmic_density=r,tension=t)
            design=SimpleNamespace(angularity=a,mass=m,openness=o)
            with patch('cover_engine.song_symbol.design_from_music',return_value=design):
                title=next(cues[0] for motif,cues in IMAGERY if motif==name)
                first,layout=compose_song_symbol(base,dna,title)
                second,again=compose_song_symbol(base,dna,title)
            self.assertEqual(layout['motif'],name)
            self.assertEqual(first.tobytes(),second.tobytes())
            self.assertEqual(layout,again)
            bounds=ImageChops.difference(base,first).getbbox()
            self.assertIsNotNone(bounds)
            self.assertGreaterEqual(min(bounds[:2]),0)
            self.assertLessEqual(max(bounds[2:]),384)
            self.assertLess((layout['bounds'][2]-layout['bounds'][0])*(layout['bounds'][3]-layout['bounds'][1]),384*384*.30)
            results.append(first.tobytes())
        self.assertEqual(len(set(results)),len(results))

    def test_same_symbol_changes_with_audio_and_title_avoids_it(self):
        soft=replace(self.dna,roughness=.1,arousal=.25,rhythmic_density=.1,attack_strength=.1)
        hard=replace(self.dna,roughness=.8,arousal=.9,rhythmic_density=.85,attack_strength=.9,crest_factor=.1)
        base=Image.new("RGB",(600,600),"#3f6874")
        first,layout=compose_song_symbol(base,soft,"Feather")
        second,second_layout=compose_song_symbol(base,hard,"Feather")
        self.assertEqual(layout['motif'],'feather')
        self.assertEqual(second_layout['motif'],'feather')
        self.assertNotEqual(first.tobytes(),second.tobytes())
        lettering={}
        music2picture._add_cover_text(first,"Ночной Свет / Nightfall","Artist",text_mode="title_artist",
                                     language="mixed",visual_dna=soft,layout_out=lettering,symbol_layout=layout)
        self.assertEqual(intersection_fraction(lettering["ink_bounds"],layout["bounds"]),0)
        self.assertGreaterEqual(lettering["contrast_ratio"],4.5)

    def test_public_export_includes_symbol_and_profile_even_without_title(self):
        bundle=AnalysisBundle(self.analysis,self.dna,"Description","Brief",build_visual_plan(self.dna),"en",())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);audio=root/"Another Love.mp3";audio.touch()
            with patch("music2picture.require_ffmpeg"), \
                 patch("music_metadata.read_all_metadata",return_value={"title":"Another Love"}), \
                 patch.object(music2picture.DEFAULT_PIPELINE,"analyse",return_value=bundle), \
                 patch("music2picture.DescriptionStore.put"), \
                 patch("music2picture.render_variant",return_value=Image.new("RGB",(384,384),"#285873")):
                target=music2picture.make_cover(audio,root/"cover.png",size=384,text_mode="none")
            profile=json.loads((root/".sonicforge/cover.profile.json").read_text(encoding="utf-8"))
            self.assertEqual(profile["song_symbol"]["motif"],"heart")
            with Image.open(target) as result:
                self.assertIsNotNone(ImageChops.difference(result,Image.new("RGB",result.size,"#285873")).getbbox())


if __name__ == "__main__":
    unittest.main()
