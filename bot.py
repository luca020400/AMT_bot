#!/usr/bin/env python3

import datetime
import json
import logging
import re
import sqlite3
import urllib.parse
import urllib.request
from math import asin, cos, floor, radians, sin, sqrt

from bs4 import BeautifulSoup
from telegram import ParseMode, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (CommandHandler, ConversationHandler, Filters,
                          MessageHandler, Updater)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

url_stops = 'http://www.amt.genova.it/amt/servizi/passaggi_i.php?CodiceFermata='
url_line = 'http://www.amt.genova.it/amt/servizi/orari_tel.php'

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


# Download the AMT pages
def download_stops(code):
    with urllib.request.urlopen(url_stops + code) as response:
        return response.read()


def download_line(line):
    today = datetime.datetime.today()
    params = urllib.parse.urlencode({
        'linea': line,
        'gg': today.day,
        'mm': today.month,
        'aa': today.year,
        'cmdOrari': 'Mostra+Orari',
    }).encode("utf-8")
    with urllib.request.urlopen(url_line, params) as response:
        return response.read()


# Parse the HTML in a JSON object
def parse_stops(html):
    soup = BeautifulSoup(html, "lxml")

    font = soup.find_all('font')[1].text
    trs = soup.find_all('tr')

    json_stops = {
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
            json_stops["stops"].append(stop)

    return json_stops


def parse_line(html):
    soup = BeautifulSoup(html, "lxml")

    headlines = list(filter(lambda x:
                            not x.text.startswith("Orari") and not x.text.startswith("LINEA"), soup.find_all('font')))
    tables = soup.find_all('table')

    json_line = []

    for counter, table in enumerate(filter(lambda x: not len(x.find_all("td")) == 0, tables)):
        times = []
        tds = table.find_all("td")
        for td in tds:
            times.append(td.text)

        line = {
            "direction": headlines[counter].text,
            "times": times,
        }
        json_line.append(line)

    return json_line


# Create a nice message from the JSON object
def beautify_stops(json_stops):
    if len(json_stops["stops"]) == 0:
        return "Nessun transito", None

    message = "`" \
        "Fermata          : " + json_stops["name"] + "\n\n"
    for stop in json_stops["stops"]:
        message += "Numero Autobus   : " + stop["line"] + "\n" \
            "Direzione        : " + stop["dest"] + "\n" \
            "Orario di arrivo : " + stop["time"] + "\n" \
            "Tempo rimanente  : " + stop["eta"] + "\n\n"
    message += "`"

    return message, ParseMode.MARKDOWN


def beautify_line(line_json):
    if len(line_json) == 0:
        return "Linea inesistente", None

    message = "`"
    for line in line_json:
        message += line["direction"] + "\n"
        for i in range(0, len(line["times"])):
            message += line["times"][i] + \
                (", " if i != len(line["times"]) - 1 else "")
        message += "\n\n"
    message += "`"

    return message, ParseMode.MARKDOWN


def get_location_number(chat_id):
    number = query_db(
        'select location_number from user_data where chat_id=? limit 10', [chat_id])
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


def get_nearests(longitude, latitude, number):
    nearest_stops = []
    for stop in stops:
        nearest_stops.append({
            "stop": stop,
            "distance": haversine(stop["longitude"], stop["latitude"], longitude, latitude)
        })
    nearest_stops = sorted(
        nearest_stops, key=lambda k: k.get('distance', 0))[:number]
    return nearest_stops


def handle_line(bot, update):
    page = download_line(update.message.text)
    line_json = parse_line(page)
    message, mode = beautify_line(line_json)
    bot.send_message(chat_id=update.message.chat_id,
                     text=message,
                     parse_mode=mode)


def handle_code(bot, update):
    page = download_stops(update.message.text)
    stops_json = parse_stops(page)
    message, mode = beautify_stops(stops_json)
    bot.send_message(chat_id=update.message.chat_id,
                     text=message,
                     parse_mode=mode)


def handle_code_or_line(bot, update):
    if re.match(r"^\d{4}$", update.message.text):
        handle_code(bot, update)
    elif re.match(r"^\d*", update.message.text):
        handle_line(bot, update)
    else:
        bot.send_message(chat_id=update.message.chat_id,
                         text="Codice non valido")


def handle_location(bot, update):
    number = get_location_number(update.message.chat_id)
    message = "Fermata più vicina : \n" if number == 1 else "Fermate più vicine : \n"
    nearest_stops = get_nearests(update.message.location.longitude,
                                 update.message.location.latitude,
                                 number)
    for stop in nearest_stops:
        message += "Nome : " + stop["stop"]["name"] + "\n" \
            "Codice : " + stop["stop"]["code"] + "\n" \
            "Distanza : " + str(floor(stop["distance"] * 1000)) + " metri\n\n"
    bot.send_message(chat_id=update.message.chat_id,
                     text=message)
    bot.send_location(chat_id=update.message.chat_id,
                      longitude=nearest_stops[0]["stop"]["longitude"],
                      latitude=nearest_stops[0]["stop"]["latitude"])


def start(bot, update):
    bot.send_message(chat_id=update.message.chat_id,
                     text="Ricevi informazioni sulle fermate degli autobus AMT a Genova.\n"
                          "Puoi inviare il codice della fermata e riceverai la lista delle prossime fermate."
                          "Puoi inviare il numero dell'autobus e riceverai la lista delle partenze dai capolinea."
                          "Puoi inviare la tua posizione GPS per ricevere approssimativamente le informazioni della "
                          "fermata più vicina.")


keyboard = [
    ['7', '8', '9'],
    ['4', '5', '6'],
    ['1', '2', '3'],
]

markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

NUMBER = range(1)


def set_stops_number(bot, update):
    number = int(update.message.text)
    cur = database.cursor()
    cur.execute("replace into user_data values (?,?)",
                (update.message.chat_id, number))
    database.commit()
    cur.close()
    bot.send_message(chat_id=update.message.chat_id,
                     text="Impostazione salvate")
    return ConversationHandler.END


def set_stops_number_start(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text="Inserisci il numero di fermate vicino a te che vuoi vedere "
                                                          "qundo invii la tua posizione", reply_markup=markup)
    return NUMBER


def cancel(_, update):
    update.message.reply_text(
        "Impostazione non salvate", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def main():
    key = open("key.txt", "r").read().strip()
    updater = Updater(key)

    stops_number_handler = ConversationHandler(
        entry_points=[CommandHandler(
            'numero_fermate', set_stops_number_start)],

        states={
            NUMBER: [MessageHandler(Filters.text, set_stops_number)]
        },

        fallbacks=[CommandHandler('cancel', cancel)]
    )

    updater.dispatcher.add_handler(stops_number_handler)
    updater.dispatcher.add_handler(CommandHandler('start', start))
    updater.dispatcher.add_handler(
        MessageHandler(Filters.text, handle_code_or_line))
    updater.dispatcher.add_handler(
        MessageHandler(Filters.location, handle_location))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
