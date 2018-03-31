#!/usr/bin/env python3

import json
import re
from bs4 import BeautifulSoup

markers = open("markers.xml", "r").read().strip()
soup = BeautifulSoup(markers, "lxml")
markers = soup.find_all('marker')

stops = {
    "stops": []
}

for marker in markers:
    stop = {
        "code": re.findall(r"^\d{4}", marker.get("label"))[0],
        "latitude": marker.get("lat"),
        "longitude": marker.get("lng"),
    }
    stops["stops"].append(stop)

with open('stops.json', 'w') as outfile:
    json.dump(stops, outfile, indent=4)
