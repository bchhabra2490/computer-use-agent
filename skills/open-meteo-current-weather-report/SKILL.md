---
name: open-meteo-current-weather-report
description: >-
  Fetches current weather for a named city (via Open‑Meteo geocoding + forecast), posts a short mid-task update, and produces a final concise report (temperature, conditions, humidity, wind, precipitation chance) with a saved JSON snapshot. Use when you need a reproducible, scriptable weather check on macOS.
---

## Steps

1. Prepare: choose the city name (e.g., "New Delhi, India") and open Terminal (Cmd+Space → type Terminal → Enter).

2. Geocode the city (find lat/lon and timezone).

   - Run (replace CITY with a URL-encoded city name, e.g. New%20Delhi):

     curl -s "https://geocoding-api.open-meteo.com/v1/search?name=CITY&count=1&language=en&format=json" > ~/Desktop/geocode.json

   - Inspect result and ensure a match was found:

     python3 - <<'PY'
import json,sys
j=json.load(open('/Users/' + __import__('os').getlogin() + '/Desktop/geocode.json'))
if not j.get('results'):
    print('No geocoding result; open ~/Desktop/geocode.json to inspect and retry with a clearer name.'); sys.exit(1)
r=j['results'][0]
print(r['name'], r.get('country',''), 'lat=', r['latitude'], 'lon=', r['longitude'], 'timezone=', r.get('timezone'))
PY

   - Note the latitude, longitude, and timezone (you will use them for the forecast call).

3. Fetch the current-weather + precipitation-probability for that location.

   - Copy the latitude and longitude from step 2 into LAT and LON. Use Asia/Kolkata for India time alignment or the timezone returned by geocoding.

   - Recommended curl (this requests current meteorological fields plus hourly precipitation probability):

     LAT=28.62137
     LON=77.2148
     TZ=Asia%2FKolkata
     curl -s "https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}&current_weather=true&hourly=precipitation_probability&timezone=${TZ}&temperature_unit=celsius&windspeed_unit=kmh" > ~/Desktop/forecast.json

   - If you prefer the more detailed current fields used by the example, use:

     curl -s "https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,precipitation&hourly=precipitation_probability&forecast_days=1&timezone=${TZ}" > ~/Desktop/forecast.json

4. Produce a short mid-task update as soon as you have the fetched data.

   - Run a quick extractor to print the key current values and timestamp; paste the one-line mid-task update into your active chat, note app, or save to ~/Desktop/weather-mid-update.txt.

     python3 - <<'PY'
import json,os
f='/Users/'+os.getlogin()+'/Desktop/forecast.json'
j=json.load(open(f))
# Try current_weather first (simple API form)
cur=j.get('current_weather')
if cur:
    temp=cur.get('temperature')
    wind=cur.get('windspeed')
    wdir=cur.get('winddirection')
    time=cur.get('time')
    # precipitation probability may be in hourly; find matching hour
    pp= None
    try:
        import datetime
        hr=j.get('hourly',{})
        times=hr.get('time',[])
        probs=hr.get('precipitation_probability',[])
        if times and probs:
            idx=times.index(time)
            pp=probs[idx]
    except Exception:
        pp=None
    cond = 'weather_code:'+str(cur.get('weathercode'))
    s=f"Mid-update: {temp}°C at {time}, {cond}, wind {wind} km/h, precip chance {pp}%"
else:
    # fallback to the detailed-current form
    cur2=j.get('current')
    if cur2:
        temp=cur2.get('temperature_2m')
        hum=cur2.get('relative_humidity_2m')
        wind=cur2.get('wind_speed_10m')
        time=cur2.get('time')
        s=f"Mid-update: {temp}°C at {time}, humidity {hum}%, wind {wind} km/h"
    else:
        s='Could not find current-weather fields in forecast.json; open the file to inspect.'
print(s)
open('/Users/'+os.getlogin()+'/Desktop/weather-mid-update.txt','w').write(s+"\n")
PY

   - Post the printed line to your chat or include it in your notes. This satisfies the "short mid-task update when you have the data" requirement.

5. Create the final concise report.

   - Run the final extractor that prints a one-paragraph summary including: exact source (Open‑Meteo), timestamp (local timezone), temperature, textual condition (map weather_code to text, see Tips), humidity (if available), wind speed and direction, and the current-hour precipitation probability.

     python3 - <<'PY'
import json,os
f='/Users/'+os.getlogin()+'/Desktop/forecast.json'
j=json.load(open(f))
# simple weather_code -> text (subset)
wc_map={
  0:'Clear',1:'Mainly clear',2:'Partly cloudy',3:'Overcast',
  45:'Fog',48:'Depositing rime fog',
  51:'Light drizzle',53:'Moderate drizzle',55:'Dense drizzle',
  61:'Slight rain',63:'Moderate rain',65:'Heavy rain',
  71:'Slight snow',73:'Moderate snow',75:'Heavy snow',
  95:'Thunderstorm',96:'Thunderstorm with slight hail',99:'Thunderstorm with heavy hail'
}
out=[]
cur=j.get('current_weather')
if cur:
    temp=cur.get('temperature')
    time=cur.get('time')
    wc=cur.get('weathercode')
    cond=wc_map.get(wc,f'code {wc}')
    wind=cur.get('windspeed')
    wdir=cur.get('winddirection')
    # precipitation probability for the hour
    pp=None
    try:
        times=j.get('hourly',{}).get('time',[])
        probs=j.get('hourly',{}).get('precipitation_probability',[])
        if times and probs:
            idx=times.index(time)
            pp=probs[idx]
    except Exception:
        pp=None
    # humidity may not be in current_weather; check hourly or detailed current
    hum=None
    if j.get('hourly') and 'relativehumidity_2m' in j['hourly']:
        try:
            hum_arr=j['hourly']['relativehumidity_2m']
            hum=hum_arr[idx]
        except Exception:
            hum=None
    # format wind direction into compass
    def dir_to_compass(d):
        if d is None: return ''
        dirs=['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']
        ix=int((d%360)/22.5)
        return dirs[ix]
    wcomp=dir_to_compass(wdir)
    report=f"Source: Open-Meteo | Time: {time} | Temp: {temp}°C | Conditions: {cond} | Humidity: {hum if hum is not None else 'n/a'}% | Wind: {wind} km/h {wcomp} | Precip chance: {pp if pp is not None else 'n/a'}%"
    print(report)
    open('/Users/'+os.getlogin()+'/Desktop/weather-final-report.txt','w').write(report+'\n')
else:
    print('No current_weather found; open ~/Desktop/forecast.json to inspect.')
PY

   - Copy the printed line and deliver it to the requester (chat, email, note). The script also saves the final one-line report to ~/Desktop/weather-final-report.txt.

6. Save verification artifacts (optional but recommended).

   - Keep ~/Desktop/geocode.json and ~/Desktop/forecast.json as the raw API responses for traceability.
   - Optionally take a screenshot of the JSON in Preview/Chrome: open the file in Preview and use Cmd+Shift+4 to capture, or use the Screenshot app (Cmd+Shift+5).

## Tips

- The skill uses Open‑Meteo (https://open-meteo.com) which is free and stable for quick checks. For production or high-frequency queries, consider a paid weather API.
- If python3 is not available, you can open the saved .json files in Google Chrome or Preview and inspect manually.
- The Open‑Meteo `current_weather` block contains a compact set of fields; some detailed fields (relative humidity, apparent temperature) may appear only when requested via the `current=` parameter or in `hourly` arrays. Use the detailed-parameter curl command in step 3 if you need those exact fields.
- The script includes a small weather_code → text mapping. Extend it if you need more precise wording.
- Always include the API timestamp/timezone in your final report so recipients know the observation time.

Use this skill whenever you need a repeatable, verifiable current-weather check for a city from the macOS desktop.
