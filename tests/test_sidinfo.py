#!/usr/bin/python3

import os
import tempfile
import urllib.request
import unittest
from desidulate import sidinfo


class SidInfoTestCase(unittest.TestCase):

    def run_sidinfo(self, sidfile):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_sidfile = os.path.join(tmpdir, 'test.sid')
            with open(temp_sidfile, 'wb') as f:
                with urllib.request.urlopen(f'http://www.hvsc.c64.org/download/{sidfile}') as r:
                    f.write(r.read())
            results = []
            for result in sidinfo.sidinfo(temp_sidfile):
                del result['path']
                results.append(result)
            return results

    def test_sidinfo(self):
        for sidfile, expected_result in (
                ('C64Music/MUSICIANS/K/Kyd_Jesper/Zargon_02.sid', [{'magicID': 'PSID', 'version': 2, 'dataOffset': 124, 'loadAddress': 0, 'initAddress': 49152, 'playAddress': 49184, 'songs': 1, 'startSong': 1, 'speed': 'CIA', 'name': 'Zargon #02', 'author': 'Jesper Kyd (Joe)', 'released': '1987 Zargon', 'binformat': 'built-in', 'psidSpecific': 'c64', 'clock': 'PAL', 'sidmodel': 'Unknown', 'sidmodel2': 'Unknown', 'sidmodel3': 'Unknown', 'startPage': 8, 'pageLength': 152, 'secondSIDAddress': 0, 'thirdSIDAddress': 0, 'pal': 1, 'sids': 1, 'cia': 19456, 'song': 1}]),
                ('C64Music/MUSICIANS/H/Hubbard_Rob/Commando.sid', [{'magicID': 'PSID', 'version': 2, 'dataOffset': 124, 'loadAddress': 0, 'initAddress': 24498, 'playAddress': 20498, 'songs': 19, 'startSong': 1, 'speed': 'VBI', 'name': 'Commando', 'author': 'Rob Hubbard', 'released': '1985 Elite', 'binformat': 'built-in', 'psidSpecific': 'c64', 'clock': 'PAL', 'sidmodel': '6581', 'sidmodel2': 'Unknown', 'sidmodel3': 'Unknown', 'startPage': 0, 'pageLength': 0, 'secondSIDAddress': 0, 'thirdSIDAddress': 0, 'pal': 1, 'sids': 1, 'cia': 0, 'song': song} for song in range(1, 19+1)]),
                ('C64Music/MUSICIANS/L/Linus/Ride_the_High_Country.sid', [{'magicID': 'PSID', 'version': 2, 'dataOffset': 124, 'loadAddress': 0, 'initAddress': 4086, 'playAddress': 4099, 'songs': 1, 'startSong': 1, 'speed': 'CIA', 'name': 'Ride the High Country', 'author': 'Sascha Zeidler (Linus)', 'released': '2006 Triad/Viruz', 'binformat': 'built-in', 'psidSpecific': 'c64', 'clock': 'PAL', 'sidmodel': '8580', 'sidmodel2': 'Unknown', 'sidmodel3': 'Unknown', 'startPage': 0, 'pageLength': 0, 'secondSIDAddress': 0, 'thirdSIDAddress': 0, 'pal': 1, 'sids': 1, 'cia': 4913, 'song': 1}]),
                ('C64Music/MUSICIANS/G/Goto80/Automatas.sid', [{'magicID': 'PSID', 'version': 2, 'dataOffset': 124, 'loadAddress': 0, 'initAddress': 4048, 'playAddress': 4067, 'songs': 1, 'startSong': 1, 'speed': 'CIA', 'name': 'Automatas', 'author': 'Anders Carlsson (Goto80)', 'released': '2009 Oxsid Planetary', 'binformat': 'built-in', 'psidSpecific': 'c64', 'clock': 'PAL', 'sidmodel': '8580', 'sidmodel2': 'Unknown', 'sidmodel3': 'Unknown', 'startPage': 0, 'pageLength': 0, 'secondSIDAddress': 0, 'thirdSIDAddress': 0, 'pal': 1, 'sids': 1, 'cia': 2456, 'song': 1}]),
                ('C64Music/MUSICIANS/S/Surgeon/Nice_Dream_2SID.sid', [{'magicID': 'PSID', 'version': 3, 'dataOffset': 124, 'loadAddress': 0, 'initAddress': 4096, 'playAddress': 4099, 'songs': 1, 'startSong': 1, 'speed': 'VBI', 'name': 'Nice Dream', 'author': 'Przemek Mroczkowski (Surgeon)', 'released': '2007 Vulture Design', 'binformat': 'built-in', 'psidSpecific': 'c64', 'clock': 'PAL', 'sidmodel': '8580', 'sidmodel2': '8580', 'sidmodel3': 'Unknown', 'startPage': 0, 'pageLength': 0, 'secondSIDAddress': 66, 'thirdSIDAddress': 0, 'pal': 1, 'sids': 2, 'cia': 0, 'song': 1}]),
                ('C64Music/MUSICIANS/H/Hermit/Tree_Angel_3SID.sid', [{'magicID': 'PSID', 'version': 4, 'dataOffset': 124, 'loadAddress': 0, 'initAddress': 4096, 'playAddress': 4099, 'songs': 1, 'startSong': 1, 'speed': 'VBI', 'name': 'The Tree Angel', 'author': 'Mihály Horváth (Hermit)', 'released': '2014 Hermit', 'binformat': 'built-in', 'psidSpecific': 'c64', 'clock': 'PAL', 'sidmodel': '8580', 'sidmodel2': '8580', 'sidmodel3': '8580', 'startPage': 0, 'pageLength': 0, 'secondSIDAddress': 66, 'thirdSIDAddress': 68, 'pal': 1, 'sids': 3, 'cia': 0, 'song': 1}]),
                ('C64Music/MUSICIANS/T/Timoc/Noisemaster_3.sid', [{'magicID': 'RSID', 'version': 2, 'dataOffset': 124, 'loadAddress': 0, 'initAddress': 49152, 'playAddress': 0, 'songs': 1, 'startSong': 1, 'speed': 'VBI', 'name': 'Noisemaster 3', 'author': 'Torsten Kruse (Timoc)', 'released': '1988 INXS', 'binformat': 'built-in', 'psidSpecific': 'c64', 'clock': 'PAL', 'sidmodel': '6581', 'sidmodel2': 'Unknown', 'sidmodel3': 'Unknown', 'startPage': 4, 'pageLength': 85, 'secondSIDAddress': 0, 'thirdSIDAddress': 0, 'pal': 1, 'sids': 1, 'cia': 16421, 'song': 1}]),
                ('C64Music/MUSICIANS/H/Hubbard_Rob/5_Title_Tunes.sid', [{'magicID': 'PSID', 'version': 2, 'dataOffset': 124, 'loadAddress': 0, 'initAddress': 2832, 'playAddress': 2880, 'songs': 5, 'startSong': 1, 'speed': speed, 'name': '5 Title Tunes', 'author': 'Rob Hubbard', 'released': '1985 Rob Hubbard', 'binformat': 'built-in', 'psidSpecific': 'c64', 'clock': 'PAL', 'sidmodel': '6581', 'sidmodel2': 'Unknown', 'sidmodel3': 'Unknown', 'startPage': 0, 'pageLength': 0, 'secondSIDAddress': 0, 'thirdSIDAddress': 0, 'pal': 1, 'sids': 1, 'cia': cia, 'song': song} for song, speed, cia in ((1, 'VBI', 0), (2, 'VBI', 0), (3, 'CIA', 16421), (4, 'VBI', 0), (5, 'VBI', 0))]),
                ):
            try:
                result = self.run_sidinfo(sidfile)
            except urllib.error.HTTPError as e:
                print("WARNING: HVSC down?: %s" % e)
                continue
            self.assertEqual(expected_result, result)


if __name__ == '__main__':
    unittest.main()
