#!/usr/bin/env python3

import json
import logging
import re
import urllib.request
import sqlite3
from math import asin, cos, floor, radians, sin, sqrt

from bs4 import BeautifulSoup
from telegram import ParseMode
from telegram.ext import CommandHandler, Filters, MessageHandler, Updater

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

url = 'http://www.amt.genova.it/amt/servizi/passaggi_i.php?CodiceFermata='

stops = json.load(open('stops.json'))
database = sqlite3.connect('database.db', check_same_thread=False)


# Utility functions
def init_db():
    with open('schema.sql', mode='r') as f:
        database.cursor().executescript(f.read())
    database.commit()


def query_db(query, args=(), one=False):
    cur = database.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


# Download the AMT page
def download(code):
    with urllib.request.urlopen(url + code) as response:
        return response.read()


# Parse the HTML in a JSON object
def parse(html):
    soup = BeautifulSoup(html, "lxml")

    font = soup.find_all('font')[1].text
    trs = soup.find_all('tr')

    json_message = {
        "name": font,
        "stops": []
    }

    for tr in trs:
        tds = tr.find_all("td")
        if len(tds) == 4:
            stop = {
                "line": tds[0].text,
                "dest": tds[1].text,
                "time": tds[2].text,
                "eta": tds[3].text,
            }
            json_message["stops"].append(stop)

    return json_message


# Create a nice message from the JSON object
def beautify(stops_json):
    if len(stops_json["stops"]) == 0:
        return "Nessun transito", None

    message = "`"
    message += "Fermata          : " + stops_json["name"] + "\n\n"
    for stop in stops_json["stops"]:
        message += "Numero Autobus   : " + stop["line"] + "\n"
        message += "Direzione        : " + stop["dest"] + "\n"
        message += "Orario di arrivo : " + stop["time"] + "\n"
        message += "Tempo rimanente  : " + stop["eta"] + "\n\n"
    message += "`"

    return message, ParseMode.MARKDOWN


def get_location_number(chat_id):
    number = query_db('select location_number from user_data where chat_id=?', [chat_id])
    if not number:
        return 1
    return number[0][0]


def haversine(lon1, lat1, lon2, lat2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(
        radians, [float(lon1), float(lat1), float(lon2), float(lat2)])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers. Use 3956 for miles
    return c * r


def get_nearests(longitude, latitude, number=1):
    nearest_stops = []
    for stop in stops:
        nearest_stops.append({
            "stop": stop,
            "distance": haversine(stop["longitude"], stop["latitude"], longitude, latitude)
        })
    nearest_stops = sorted(nearest_stops, key=lambda k: k.get('distance', 0))[:number]
    return nearest_stops


def handle_code(bot, update):
    if not re.match(r"^\d{4}$", update.message.text):
        bot.send_message(chat_id=update.message.chat_id,
                         text="Codice non valido")
        return
    page = download(update.message.text)
    json_message = parse(page)
    message, mode = beautify(json_message)
    bot.send_message(chat_id=update.message.chat_id,
                     text=message,
                     parse_mode=mode)


def handle_location(bot, update):
    message = "Fermate più vicine : \n"
    nearest_stops = get_nearests(update.message.location.longitude,
                                 update.message.location.latitude,
                                 get_location_number(update.message.chat_id))
    for stop in nearest_stops:
        message += "Nome : " + stop["stop"]["name"] + "\n"
        message += "Codice : " + stop["stop"]["code"] + "\n"
        message += "Distanza : " + str(floor(stop["distance"] * 1000)) + " metri\n\n"
    bot.send_message(chat_id=update.message.chat_id,
                     text=message)
    bot.send_location(chat_id=update.message.chat_id,
                      longitude=nearest_stops[0]["stop"]["longitude"],
                      latitude=nearest_stops[0]["stop"]["latitude"])


def start(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text="""Ricevi informazioni sulle fermate degli autobus AMT a Genova.\n
Puoi inviare il codice della fermata e riceverai la lista delle prossime fermate.
Puoi inviare la tua posizione GPS per ricevere approssimativamente le informazioni della fermata più vicina.""")


def set_stops_number(bot, update, args):
    cur = database.cursor()
    cur.execute("replace into user_data values (?,?)", (update.message.chat_id, int(args[0])))
    database.commit()
    cur.close()
    bot.send_message(chat_id=update.message.chat_id, text="Impostazione salvate")


def main():
    key = open("key.txt", "r").read().strip()
    updater = Updater(key)

    updater.dispatcher.add_handler(CommandHandler('start', start))
    updater.dispatcher.add_handler(CommandHandler('numero_fermate', pref, pass_args=True))
    updater.dispatcher.add_handler(MessageHandler(Filters.text, handle_code))
    updater.dispatcher.add_handler(
        MessageHandler(Filters.location, handle_location))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
