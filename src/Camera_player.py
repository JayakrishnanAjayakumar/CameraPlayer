from subprocess import check_output
import pynmea2
import gpxpy
import gpxpy.gpx
import os
import time as t
from dateutil.parser import parse
import design
import sys
import json
import simplekml
#pyqt imports
from PyQt5.QtWidgets import QApplication, QMainWindow,QFileDialog
from PyQt5.QtCore import QUrl,pyqtSlot
from collections import OrderedDict
from scipy.spatial import cKDTree
from shapely.geometry import Point,LineString,Polygon,mapping
from fiona import collection
from fiona.crs import from_epsg
from os.path import dirname
from glob import glob
csv_header="media time,time,latitude,longitude,elevation [m],speed [knots],heading,variation,position dilution,horizontal dilution,vertical dilution,fix type,satellite count,valid\n"
class Gps():
    def __init__(self):
        self.filename=None
        self.created_at=None
        self.values=[]
        self.tree=None
        self.visdict=OrderedDict()
    
    def destroy(self):
        self.filename=None
        self.created_at=None
        self.values=None
        self.tree=None
        self.visdict=None
    
    def getprepopulatedvalues(self):
        datadict={}
        datadict['media_time']=""
        datadict['elev']=""
        datadict['speed']=""
        datadict['heading']=""
        datadict['variation']=""
        datadict['position_dilution']=""
        datadict['horizontal_dilution']=""
        datadict['vertical_dilution']=""
        datadict['fix_type']=""
        datadict['statellite_count']=""
        datadict['valid']=""
        datadict['timedata']=""
        datadict['lat']=""
        datadict['lon']=""
        datadict['course']=""
        datadict['geoid_height']=""
        datadict['time']=""
        return datadict
class CameraApp(QMainWindow, design.Ui_MainWindow):
    def __init__(self, parent=None):
        super(CameraApp, self).__init__(parent)
        self.setupUi(self)
        cwd = os.getcwd()
        self.webView.load(QUrl('file:///'+cwd+'/working/CameraPlayer.html'))
        self.webView.loadFinished.connect(self.finishLoading)
        self.Gps=None
        self.outputfolder=None
    @pyqtSlot()
    def finishLoading(self):
        self.webView.page().mainFrame().addToJavaScriptWindowObject("cp", self)
        
    #downloads digitzed kml from digitizer
    @pyqtSlot(str,str,result=str)
    def downloaddigitizedkml(self,datajson,filename):
        data=json.loads(datajson)
        if not filename:
            return "Error: Please provide a valid filename"
        outfile=self.outputfolder+"\\"+filename+".kml"
        kml = simplekml.Kml()
        for obj in data:
            dtyp=obj['type']
            descriptionval="category:" + obj["categ"] + " "+ "value:" + obj["val"] + " "+ "description:" + obj["desc"]
            if dtyp=='Point':
                pnt=kml.newpoint(description=descriptionval,coords=[(obj['geometry'][0],obj['geometry'][1])])
                pnt.style.iconstyle.icon.href=obj['markerurl']
            if dtyp=='Line':
                lin = kml.newlinestring(description=descriptionval,coords=[(a[0],a[1])for a in obj['geometry']])
                lin.style.linestyle.color = simplekml.Color.red
                lin.style.linestyle.width = 5
            if dtyp=='Polygon':
                polylist=[(a[0],a[1])for a in obj['geometry']]
                polylist.append((obj['geometry'][0][0],obj['geometry'][0][1]))
                poly = kml.newpolygon(description=descriptionval,outerboundaryis=polylist)
                poly.style.linestyle.color = simplekml.Color.blue
                poly.style.linestyle.width = 5
                poly.style.polystyle.color = simplekml.Color.gray
        kml.save(outfile)
        return "File successfully downloaded"
    
    #downloads digitzed shape from digitizer
    @pyqtSlot(str,str,result=str)
    def downloaddigitizedshape(self,datajson,filename):
        if not filename:
            return "Error: Please provide a valid filename"
        outcategs={}
        datum=json.loads(datajson)
        for obj in datum: 
            dtyp=obj['type']
            if dtyp=='Line':
                dtyp='LineString'
            if dtyp not in outcategs:
                outcategs[dtyp]=[]
            d={'geometry':0,'properties':{}}
            if(dtyp=='Point'):
                geom=Point(obj['geometry'][0],obj['geometry'][1])
            elif(dtyp=='LineString'):
                geom=LineString([(a[0],a[1])for a in obj['geometry']])
            elif(dtyp=='Polygon'):
                geom=Polygon([(a[0],a[1])for a in obj['geometry']])
            d['geometry']=mapping(geom)
            d['properties']['category']=obj['categ']
            d['properties']['value']=obj['val']
            d['properties']['description']=obj['desc']
            outcategs[dtyp].append(d)
        for types in outcategs:
            outfile=self.outputfolder+"\\"+filename+"_"+types+".shp"
            schema = {'geometry':types,'properties': {'category': 'str','value': 'str','description':'str'}}
            with collection(outfile, "w", "ESRI Shapefile", schema, crs=from_epsg(4326)) as output:
                for dat in outcategs[types]:
                    output.write(dat)
        return "File Successfully Downloaded"

    @pyqtSlot(result=str)
    def upload(self):
        dataobj={}
        self.Gps=None
        self.Gps=Gps()
        self.Gps.filename=None
        fileName, _ = QFileDialog.getOpenFileName(self, "Select Video File",
                '', "Videos (*.mp4 *.MP4 *.mov *.MOV)")
        if not fileName or (not fileName.lower().endswith('mp4') and not fileName.lower().endswith('mov')):
            dataobj['Error']="Missing File name or wrong file format (.mp4 and .mov)"
            dataobj['filename']=""
            return json.dumps(dataobj)
        self.Gps.filename=fileName
        dataobj['filename']=fileName
        self.extractdata(self.Gps)
        spatialdata= list(self.Gps.visdict.values())
        if len(spatialdata)!=0:
            self.Gps.tree=cKDTree(spatialdata)
        dataobj['Error']=""
        dataobj['mediamap']=self.Gps.visdict
        return json.dumps(dataobj)
    
    @pyqtSlot(int,int,str,int,result=str)
    def syncdata(self,gpsindex,videotimeinsecs,syncfile,totalduration):
        gpxobject=gpxpy.parse(open(syncfile),version=1.1)
        self.Gps=None
        self.Gps=Gps()
        dataarr=[]
        dataobj={}
        for track in gpxobject.tracks:
            for segment in track.segments:
                for point in segment.points:
                    dataarr.append(point)
        for i in range(len(dataarr)):
            current=dataarr[i].time
            sync=dataarr[gpsindex].time
            tdelta=(current.hour*3600+current.minute*60+current.second)-(sync.hour*3600+sync.minute*60+sync.second)
            diff=videotimeinsecs+tdelta
            if diff>=0 and diff<=totalduration and diff not in self.Gps.visdict:
                self.Gps.visdict[diff]=[dataarr[i].longitude,dataarr[i].latitude]
                datadict=self.Gps.getprepopulatedvalues()
                datadict['timedata']=current
                datadict['lat']=dataarr[i].latitude
                datadict['lon']=dataarr[i].longitude
                datadict['time']=str(current)
                datadict['media_time']=t.strftime("%#H:%M:%S", t.gmtime(diff))
                self.Gps.values.append(datadict)
        spatialdata= list(self.Gps.visdict.values())
        if len(spatialdata)!=0:
            self.Gps.tree=cKDTree(spatialdata)
        dataobj['mediamap']=self.Gps.visdict
        return json.dumps(dataobj)
    @pyqtSlot(result=str)
    def parseuploadedgpx(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Select GPX File",
                '', "GPX (*.gpx *.GPX)")
        parsedgpx={}
        if not fileName:
            parsedgpx['Error']='No files uploaded'
            return json.dumps(parsedgpx)
        gpxcontent=open(fileName).read()
        gpxobject=None
        try:
            gpxobject=gpxpy.parse(gpxcontent,version=1.1)
        except:
            gpxobject=None
        if gpxobject is None:
            parsedgpx['Error']='Cannot Parse GPX'
            return json.dumps(parsedgpx)
        parsedgpx['coordinates']=[]
        for track in gpxobject.tracks:
            for segment in track.segments:
                for point in segment.points:
                    parsedgpx['coordinates'].append({'lat':point.latitude,'lng':point.longitude})
        parsedgpx['gpsfilename']=fileName
        parsedgpx['Error']=""
        return json.dumps(parsedgpx)
    
    @pyqtSlot()
    def clearcurrentdata(self):
        if(self.Gps is not None):
            self.Gps.destroy()
            self.Gps=None
        
    
    @pyqtSlot(str,result=int)
    def getclosesttime(self,coords):
        coords=list(map(float,coords.split(',')))
        d,i=self.Gps.tree.query(coords)
        return list(self.Gps.visdict.keys())[i]
    
    @pyqtSlot(result=str)
    def browse_folder(self):
        folderName = str(QFileDialog.getExistingDirectory(self, "Select Directory"))
        if( not folderName):
            folderName=""
        self.outputfolder=folderName
        return folderName

    @pyqtSlot(str,result=str)
    def downloadcsv(self,filename):
        finalfilename=self.outputfolder+"/"+filename+".csv"
        out_file_csv=open(finalfilename,'w')
        out_file_csv.write(csv_header)
        for dat in self.Gps.values:
            out_file_csv.write(str(dat['media_time'])+","+str(dat['time'])+","+str(dat['lat'])+","+str(dat['lon'])+","+str(dat['elev'])+","+str(dat['speed'])+","+str(dat['heading'])+","+str(dat['variation'])+","+str(dat['position_dilution'])+","+str(dat['horizontal_dilution'])+","+str(dat['vertical_dilution'])+","+str(dat['fix_type'])+","+str(dat['statellite_count'])+","+str(dat['valid'])+"\n")
        out_file_csv.close()
        return "File successfully downloaded"
    
    
    @pyqtSlot(str,result=str)
    def downloadgps(self,filename):
        finalfilename=self.outputfolder+"/"+filename+".gpx"
        out_file_gpx=open(finalfilename,'w')
        gpx = gpxpy.gpx.GPX()
        gpx_track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(gpx_track)
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)
        for dat in self.Gps.values:
            trkpoint=gpxpy.gpx.GPXTrackPoint(latitude=dat['lat'], longitude=dat['lon'], elevation=dat['elev'],time=dat['timedata'],speed=dat['speed'],horizontal_dilution=dat['horizontal_dilution'],vertical_dilution=dat['vertical_dilution'],position_dilution=dat['position_dilution'])
            trkpoint.course=dat['course']
            trkpoint.satellites=dat['statellite_count']
            trkpoint.geoid_height =dat['geoid_height']
            extensions={}
            extensions['mediatime']=dat['media_time']
            extensions['valid']=dat['valid']
            trkpoint.extensions=extensions
            gpx_segment.points.append(trkpoint)
        out_file_gpx.write(gpx.to_xml(version='1.1'))
        out_file_gpx.close()
        return "File successfully downloaded"

    def converttimestringtoseconds(self,media_time):
        k=parse(media_time,fuzzy=True)
        return k.hour*3600+(k.minute*60)+(k.second)
     
    def extractdata(self,Gps):
        has_exif_tags=False
        filename=Gps.filename
        try:
            out = check_output(['exiftool.exe', '-ee' ,'-G1', filename]).decode("utf-8") 
        except:
            out = check_output(['exiftool.exe', '-ee' ,'-G1', filename]).decode("ISO-8859-1")    
        lines=out.split('\n')
        timedict=None
        for i,l in enumerate(lines):
            if 'QuickTime' in l and 'Create Date' in l:
                Gps.created_at=l.split(':',1)[1].strip().split()[0].replace(':','-')
            datadict=Gps.getprepopulatedvalues()
            #for contour in NMEA format
            start=l.find('$GPGGA')
            if start!=-1:
                has_exif_tags=True
                msggpgg=None
                msggprmc=None
                #if can't read the format get to next line
                try:
                    stripl=','.join(l[start:].split(',')[:-1])
                    msggpgg = pynmea2.parse(stripl)
                    msggprmc=pynmea2.parse(l[l.find('$GPRMC'):l.find('$GPGGA')].rstrip('.'))
                except:
                    continue
                if not msggpgg.lat:
                    continue
                #safety check, latitude sometimes have issue as in $GPGGA,184722.00,410446479,N,08039.42962,W,1,05,8.44,343.5,M,-34.6,M,*66     for $GPGGA,184722.00,4104.46479,N,08039.42962,W,1,05,8.44,343.5,M,-34.6,M,*66
                try:
                    msggpgg.latitude
                    msggpgg.longitude
                except:
                    #if there is exception this is bad data and we don't want that
                    continue
                media_time=lines[i-2].split(':',1)[1].strip()
                if 's' in media_time:
                    media_time= t.strftime("%#H:%M:%S", t.gmtime(int(float(media_time.replace('s','').strip()))))
                datadict['media_time']=media_time
                time=Gps.created_at+"T"+str(msggpgg.timestamp)+"Z"
                datadict['timedata']=parse(time)
                datadict['time']=time
                datadict['elev']=msggpgg.altitude
                datadict['speed']=msggprmc.spd_over_grnd
                datadict['variation']=msggprmc.mag_variation
                datadict['horizontal_dilution']=msggpgg.horizontal_dil
                datadict['statellite_count']=msggpgg.num_sats
                datadict['valid']=(1 if msggprmc.status=='A' else 0)
                datadict['lat']=msggpgg.latitude
                datadict['lon']=msggpgg.longitude
                datadict['course']=msggprmc.true_course
                datadict['geoid_height'] =msggpgg.geo_sep
                Gps.values.append(datadict)
                Gps.visdict[self.converttimestringtoseconds(media_time)]=[datadict['lon'],datadict['lat']]
            #For small camera 
            else:
                start=l.find('$G:')
                #for myschiuva camera
                if start!=-1:
                    has_exif_tags=True
                    if timedict is None:
                        timedict={}
                    datatext=l[start:].split(':',1)[1]
                    dateval=datatext.split()[0]
                    timeval=datatext.split()[1].split('-')[0]
                    time=dateval+"T"+timeval+"Z"
                    media_time=lines[i-2].split(':',1)[1].strip()
                    if 's' in media_time:
                        media_time= t.strftime("%#H:%M:%S", t.gmtime(int(float(media_time.replace('s','').strip()))))
                    lat=datatext.split()[1].split('-')[1]
                    if lat.startswith('S'):
                        lat=float('-'+lat[1:])
                    else:
                        lat=float(lat[1:])
                    lon=datatext.split()[1].split('-')[2]
                    if lon.startswith('W'):
                        lon=float('-'+lon[1:])
                    else:
                        lon=float(lon[1:])
                    Gps.visdict[self.converttimestringtoseconds(media_time)]=[lon,lat]
                    if time not in timedict:
                        datadict['timedata']=parse(time)
                        datadict['time']=time
                        datadict['media_time']=media_time
                        datadict['lat']=lat
                        datadict['lon']=lon
                        timedict[time]=0
                        Gps.values.append(datadict)
        #could be patrol eyes, redhen etc
        if not has_exif_tags:
            currentfilenamewithoutextension=os.path.splitext(os.path.basename(filename))[0]
            #for patrol eyes
            #for patrol eyes we need to check whether the txt file exists somewhere in the path
            #start checking form parents parent directory
            txtfiles=[y for x in os.walk(dirname(dirname(dirname(filename)))) for y in glob(os.path.join(x[0], '*.txt'))]
            txtfile=None
            for tx in txtfiles:
                fname=os.path.splitext(os.path.basename(tx))[0]
                if currentfilenamewithoutextension in fname:
                    txtfile=tx
                    break
            #if we have a textfile we have successfully found the GPS associated with the video
            if txtfile is not None:
                starttime=None
                f=open(txtfile)
                for l in f:
                    if l.split()[2]=='A':
                        ind='AM'
                    else:
                        ind='PM'
                    currtime=parse(l.split()[0]+" "+l.split()[1]+ind,fuzzy=True)
                    if not starttime:
                        starttime=currtime
                    timediffinseconds=(currtime-starttime).seconds
                    splitter=l.split(',')
                    if len(splitter[0].split())==4:
                        datadict=Gps.getprepopulatedvalues()
                        lat=float(splitter[0].split()[-1])
                        lon=float(splitter[2])
                        if splitter[1]=='S':
                            lat=0-lat
                        if splitter[3].split()[0]=='W':
                            lon=0-lon
                        datadict['timedata']=currtime
                        datadict['time']=currtime.strftime("%Y-%m-%dT%H:%M:%SZ")
                        datadict['media_time']=t.strftime("%#H:%M:%S", t.gmtime(int(timediffinseconds)))
                        datadict['lat']=lat
                        datadict['lon']=lon
                        Gps.values.append(datadict)
                        Gps.visdict[int(timediffinseconds)]=[lon,lat]
                    
def main():
    app = QApplication(sys.argv)
    form = CameraApp()
    form.show()
    app.exec_()

if __name__ == '__main__':              # if we're running file directly and not importing it
    main()                              # run the main function
