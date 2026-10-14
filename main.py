import time, threading, random
from datetime import datetime
import requests
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)
flights_data = {}

def add_plane(cs, lat, lon, alt=35000, hdg=0, vel=450):
    if cs not in flights_data:
        flights_data[cs]={"trail":[],"last":{}}
    now=datetime.now().strftime("%H:%M:%S")
    flights_data[cs]["trail"].append([lat,lon])
    flights_data[cs]["trail"]=flights_data[cs]["trail"][-20:]
    flights_data[cs]["last"]={"callsign":cs,"lat":lat,"lon":lon,"alt":int(alt),"velocity":int(vel),"heading":int(hdg),"updated":now}

def track_loop():
    session=requests.Session()
    session.headers.update({"User-Agent":"Mozilla/5.0"})
    apis=[
        "https://api.adsb.lol/v2/point/{lat}/{lon}/250",
        "https://api.airplanes.live/v2/point/{lat}/{lon}/250",
        "https://api.adsb.one/v2/point/{lat}/{lon}/250"
    ]
    world_points=[
        (-1.2921,36.8219,"Nairobi"),(51.47,-0.4543,"London"),(40.71,-74.0,"New York"),
        (9,38.7,"Addis"),(0,32,"Kampala"),(25.25,55.36,"Dubai"),
        (35.68,139.76,"Tokyo"),(-33.96,18.60,"Cape Town")
    ]
    last_opensky=0
    while True:
        for template in apis:
            for lat,lon,name in world_points:
                try:
                    url=template.format(lat=lat,lon=lon)
                    rb=session.get(url, timeout=15)
                    if rb.status_code==200:
                        ac=rb.json().get("ac",[]) or []
                        for a in ac[:250]:
                            cs=(a.get("flight") or a.get("r") or "").strip().upper()
                            if not cs or len(cs)<3: continue
                            clat=a.get("lat"); clon=a.get("lon")
                            if clat is None or clon is None: continue
                            alt=a.get("alt_baro") or a.get("alt_geom") or 35000
                            if isinstance(alt,str): alt=35000
                            add_plane(cs,clat,clon,alt,a.get("track") or random.randint(0,359),a.get("gs") or 450)
                except: pass
        if time.time()-last_opensky>300:
            try:
                r=session.get("https://opensky-network.org/api/states/all", timeout=20)
                print(f"OpenSky: {r.status_code}")
                if r.status_code==200:
                    for s in (r.json().get("states") or [])[:2500]:
                        cs=(s[1] or "").strip().upper()
                        if not cs: continue
                        lon,lat,alt,vel,hdg=s[5],s[6],s[7],s[9],s[10]
                        if lat is None or lon is None: continue
                        add_plane(cs,lat,lon,alt or 35000,hdg or 0,vel or 450)
                    last_opensky=time.time()
            except: pass
        if len(flights_data)>4000:
            for k in list(flights_data.keys())[:1000]:
                del flights_data[k]
        print(f"TOTAL: {len(flights_data)}")
        time.sleep(20)

HTML="""
<!DOCTYPE html><html><head><title>v9.2 NO HUGGING</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.4.1/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.4.1/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet.markercluster@1.4.1/dist/leaflet.markercluster.js"></script>
<style>
body{margin:0;font-family:system-ui;background:#0b0e14;color:#fff}
.header{padding:10px;background:#161b27;display:flex;gap:8px;align-items:center;flex-wrap:wrap;position:sticky;top:0;z-index:999}
input{padding:10px 14px;border-radius:20px;border:1px solid #333;background:#0f1115;color:#fff;width:230px}
button{padding:10px 14px;border-radius:20px;border:none;background:#00ff88;color:#000;font-weight:bold;cursor:pointer}
button.gray{background:#2a3142;color:#fff}
#cnt{color:#00ff88;font-weight:bold}
#map{width:100%;height:72vh;background:#a0c0e0}
#tblwrap{height:22vh;overflow:auto;padding:8px;background:#11141d}
table{width:100%;font-size:12px;border-collapse:collapse}
th{color:#00ff88;position:sticky;top:0;background:#11141d;padding:6px;text-align:left}
td{padding:5px 6px;border-bottom:1px solid #1f2636}
tr:hover{background:#1d2436;cursor:pointer}
.plane-icon{font-size:22px}
</style></head><body>
<div class="header">
<b>✈️ v9.2 NO HUG</b> <span id="cnt">loading...</span>
<input id="search" placeholder="KQA BAW ETH..."><button onclick="doSearch()">Search</button>
<button class="gray" onclick="clearSearch()">Clear</button>
<button class="gray" onclick="quick('KQA')">Kenya</button>
<button class="gray" onclick="quick('BAW')">British</button>
<button class="gray" onclick="quick('ETH')">Ethiopia</button>
<button class="gray" onclick="map.setView([-1.3,36.8],6)">Nairobi</button>
<button class="gray" onclick="map.setView([20,0],2)">World</button>
</div>
<div id="map"></div>
<div id="tblwrap"><table id="tbl"></table></div>
<script>
var map = L.map('map',{worldCopyJump:true}).setView([20,0],3);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,minZoom:2}).addTo(map);

var markers = {};
var trails = {};
var clusterGroup = L.markerClusterGroup({maxClusterRadius:50, spiderfyOnMaxZoom:true, showCoverageOnHover:false});
map.addLayer(clusterGroup);
var filter = "";

function planeIcon(hdg){
  return L.divIcon({
    html: `<div style="transform: rotate(${hdg}deg);">✈️</div>`,
    className: 'plane-icon',
    iconSize: [22,22],
    iconAnchor: [11,11]
  });
}
function quick(v){document.getElementById('search').value=v; filter=v.toUpperCase(); loadData();}
function doSearch(){filter=document.getElementById('search').value.toUpperCase().trim(); loadData();}
function clearSearch(){filter=""; document.getElementById('search').value=""; loadData();}

function loadData(){
 fetch('/api/data').then(r=>r.json()).then(d=>{
  let allKeys = Object.keys(d);
  let keys = allKeys;
  if(filter) keys = allKeys.filter(k=>k.includes(filter));
  document.getElementById('cnt').innerText = `${keys.length} shown / ${allKeys.length} WORLD - zoom in to un-hug`;

  clusterGroup.clearLayers();
  markers = {};

  let html='<tr><th>Callsign</th><th>Route</th><th>Alt</th><th>Speed</th><th>Hdg</th></tr>';
  keys.slice(0,600).forEach(k=>{
   let p=d[k];
   html+=`<tr onclick="map.setView([${p.lat},${p.lon}],8)"><td><b>${p.callsign}</b></td><td>${p.callsign.substring(0,3)}</td><td>${p.alt.toLocaleString()} ft</td><td>${p.velocity} kts</td><td>${p.heading}°</td></tr>`;
   let m = L.marker([p.lat,p.lon],{icon: planeIcon(p.heading)}).bindPopup(`<b>${p.callsign}</b><br>${p.alt} ft`);
   markers[k]=m;
   clusterGroup.addLayer(m);
   if(p.trail && p.trail.length>1){
     if(trails[k]) map.removeLayer(trails[k]);
     trails[k]=L.polyline(p.trail,{color:'#00ff88',weight:1,opacity:0.4}).addTo(map);
   }
  });
  document.getElementById('tbl').innerHTML=html;
 });
}
setInterval(loadData, 4000);
loadData();
</script></body></html>
"""

@app.route("/")
def index(): return render_template_string(HTML)
@app.route("/api/data")
def api_data():
    return jsonify({k: {**v["last"], "trail": v["trail"]} for k,v in flights_data.items() if v["last"]})

if __name__=="__main__":
    threading.Thread(target=track_loop, daemon=True).start()
    print("v9.2 NO HUG http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
