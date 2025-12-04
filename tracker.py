#!/usr/bin/python3
import requests
from predictor import predict_passes
from sgp4.api import Satrec
from sgp4.api import jday
#from date import datetime, timedelta    
#from time import datetime
import os
import sys
import time
import json

def clear():
    if os.name == 'nt':  # For Windows
        _ = os.system('cls')
    else:  # For macOS and Linux
        _ = os.system('clear')


def favourite(): #This is used when a user wants to select a location from favourites
    global collected_from_ip
    collected_from_ip = False
    while True:
        try:
            print("Which of these locations do you wish to make use of? ")
            for i in favourites_list:
                print(f"{int(favourites_list.index(i)) + 1}: {i["region"]}, {i["country"]}")
            number = int(input("Select a number from the list "))
            global data
            data = favourites_list[(number - 1)] #List indexing
            break
        except ValueError:
            print("Please Select a Number! Choose Again\n")
            continue
        except TypeError:
            print("Please select a number! Choose Again!\n")
            continue
        except IndexError:
            print("You have entered a value that is not on the list! Choose Again!\n")

def add_favourite():
    while True:
        ans = input("Do you wish to add this location to favourites[Y/N] ").strip().lower()
        if ans == "y":
            print("Adding current location...")
            with open("favourites.json", "r") as f:
                favourites_list = json.load(f)
            favourites_list.append(data)
            with open("favourites.json", "w") as f:
                json.dump(favourites_list, f)
            break

        elif ans == "n":
            print("\nLocation not added to favourites")
            break
        else:
            print("\nPlease enter Y or N to continue!")
            continue




def from_ip():
    try:
        print("Getting Location now...")
        time.sleep(2)
        results = requests.get("https://ipinfo.io/json")
        # API call to get location based on IP address
        global collected_from_ip
        collected_from_ip = True

    except ConnectionError:
        while True:
            print("Please check your internet connection and try again")
            restart = input("Do you want to restart D.O.T.S? [Y or N]").strip().lower()
            if restart == "y":
                print("Restarting D.O.T.S. now...")
                os.sleep(2)
                restart_app()
                break
            elif restart == "n":
                print("Closing App now...")
                time.sleep(2)
                sys.exit()
            else:
                print("Please select Y or N")
                continue

    except TimeoutError:
        while True:
            print("The IP Server took to long to respond")
            restart = input("Do you want to restart D.O.T.S? [Y or N]").strip().lower()
            if restart == "y":
                print("Restarting D.O.T.S. now...")
                time.sleep(2)
                restart_app()
                break
            elif restart == "n":
                print("Closing App now...")
                os.sleep(2)
                sys.exit()
            else:
                print("Please select Y or N")
                continue

    except Exception as e:
        while True:
            print(f"An Error has occured: {e}")
            restart = input("Do you want to restart D.O.T.S? [Y or N]").strip().lower()
            if restart == "y":
                print("Restarting D.O.T.S. now...")
                os.sleep(2)
                restart_app()
                break
            elif restart == "n":
                print("Closing App now...")
                os.sleep(2)
                sys.exit()
            else:
                print("Please select Y or N")
                continue

            
    print("""This location is determined by your ip address.
If you are making use of VPN that masks your IP address
and gives you another IP address, this location will not
be your actual location.\n""")

    """
    This is a sample ouput of the json file from the ipinfo.io/json.com
    {
    "ip": "102.22.168.128",
    "city": "Kigali",
    "region": "Kigali",
    "country": "RW",
    "loc": "-1.9500,30.0588",
    "org": "AS36924 GVA Cote d'Ivoire SAS",
    "timezone": "Africa/Kigali",
    "readme": "https://ipinfo.io/missingauth"
    }
    """
    global data
    data = results.json() # This is the dictionary of the location information
    # This dictionary is in a variable called global variable called data.


with open("favourites.json", "r") as f:
    favourites_list = json.load(f)
if favourites_list:
    while True:
        print("How do you want you location to be gotten")
        print("1. From your IP address")
        print("2. From your favourites list.")
        fav = input("Enter 1 or 2: ")
        if fav.strip().lower() == "1":
            print("Using current location from IP")
            from_ip()
            break
        elif fav.strip().lower() == "2":
            print("\nChoosing from favourites")
            favourite()
            break
        else:
            print("Please select Y or N")
            continue
else:
    from_ip()



lat, long = data["loc"].split(",") # Stored as a tuple
(city, region, country) = (data["city"], data["region"], data["country"])


print("These are your location and coordinates.")
#Will add option for turning off autolocater and allow manual entry.
print(f"{city}, {region}, {country}")
print("Latitude:", lat)
print("Longitude:", long)

if (collected_from_ip == True) and (data not in favourites_list):
    print("Looks like this location is not in your favourites list")
    try:    
        while True:
            add_favourite()
            break
    except KeyboardInterrupt:
        print("Location Bookmark closed")



with open("selected_tle") as file:
    lines = file.readlines()
    name, line1, line2 = lines[0], lines[1], lines[2]
print("Predicting Passes...")
time.sleep(2)
predict_passes(line1, line2, lat, long)

#Add an option of do you want to run the app again.