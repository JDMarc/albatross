"""Low-rate advisory weather; never required for vehicle-dynamics authority."""
from dataclasses import dataclass
import json,math,threading,time,urllib.parse,urllib.request
@dataclass(frozen=True)
class WeatherContext:
    state:int=4
    rain:bool=False
    temperature:float|None=None
    humidity:float|None=None
    precipitation:float|None=None
    at:float=0
class WeatherService:
    def __init__(self,callback,clock=time.monotonic,fetch=None):
        self.callback=callback;self.clock=clock;self.fetch=fetch or self._fetch;self.value=WeatherContext()
        self.phone=False;self.location=None;self.phone_at=0;self.last_fetch=-1e9;self.stop_event=threading.Event()
    def phone_status(self,status):
        if status.connected and not self.phone:self.last_fetch=-1e9
        self.phone=bool(status.connected);self.phone_at=self.clock()
        if status.gps_lat is not None and status.gps_lon is not None and math.isfinite(status.gps_lat) and math.isfinite(status.gps_lon) and abs(status.gps_lat)<=90 and abs(status.gps_lon)<=180:
            self.location=(round(status.gps_lat,1),round(status.gps_lon,1))
        else:self.location=None
    @staticmethod
    def _fetch(location):
        query=urllib.parse.urlencode(dict(latitude=location[0],longitude=location[1],current="temperature_2m,relative_humidity_2m,precipitation",timezone="UTC"))
        with urllib.request.urlopen("https://api.open-meteo.com/v1/forecast?"+query,timeout=4) as response:
            return json.loads(response.read(65536))["current"]
    def poll(self):
        now=self.clock()
        if not self.phone or now-self.phone_at>15:self.value=WeatherContext(state=2);return self.value
        if self.location is None:self.value=WeatherContext();return self.value
        if now-self.last_fetch>=600:
            self.last_fetch=now
            try:
                d=self.fetch(self.location);t=float(d["temperature_2m"]);h=float(d["relative_humidity_2m"]);p=float(d["precipitation"])
                if not all(math.isfinite(x) for x in (t,h,p)) or not(-100<t<70 and 0<=h<=100 and 0<=p<1000):raise ValueError("weather data")
                self.value=WeatherContext(0,p>0,t,h,p,now)
            except (OSError,ValueError,KeyError,TypeError):self.value=WeatherContext(state=3)
        if self.value.state==0 and now-self.value.at>1200:self.value=WeatherContext(state=1)
        return self.value
    def start(self):
        def run():
            while not self.stop_event.is_set():
                context=self.poll()
                try:self.callback(context)
                except Exception:pass # weather transport cannot crash or gate the dynamics loop
                self.stop_event.wait(1)
        self.thread=threading.Thread(target=run,daemon=True,name="weather-context");self.thread.start()
    def close(self):
        self.stop_event.set()
        if hasattr(self,"thread"):self.thread.join(timeout=5)
