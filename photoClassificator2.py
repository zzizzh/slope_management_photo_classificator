import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5 import uic
import PIL.Image
import os
import shutil
import geopandas as gpd
import threading
from PIL.ExifTags import TAGS
from pandas.core.indexes.base import InvalidIndexError
from shapely.geometry import Point, Polygon
from tqdm import tqdm

class Data:
  def __init__(self, file_path, lat, lon, date):
    self.new_file_path = None            ## 새로 복사할 경로명
    self.file_path = file_path            ## 경로명
    self.point = Point(lon, lat)          ## 위도, 경도 포인트
    self.area_id = []                ## 해당 폴리곤 ID
    self.date = date

  def is_valid(self):
    if len(self.area_id) != 0:
      return True
    return False

  def set_area_id(self, area_id):
    self.area_id.append(area_id)

  def set_new_file_name(self, new_file_name):
    self.new_file_name = new_file_name

  def __lt__(self, other):
    return self.time < other.time

class Area:
  def __init__(self, polygon, area_id, area_dir_path):
    self.polygon = polygon
    self.area_id = area_id
    self.area_dir_path = area_dir_path
    self.datas = []
    self.file_num = 1


# 이미지 분류 클래스
class PhotoClassificator(threading.Thread):

  def __init__(self, root_path, gis_path, widget):
    super().__init__()
    self.root_path = root_path
    self.ext = None
    self.classificate_path = None
    self.gis_path = gis_path

    self.areas = []              # SHP에서 추출한 블록 ID, 해당 블록 내의 폴리곤 리스트 쌍
    self.file_paths = []        # 이미지 경로명 리스트
    self.datas = []            # 이미지 파일에서 추출한 메타데이터로 생성한 이미지파일명, 데이터 객체 쌍
    self.w = widget
    self.valid_data_num=0


  def printException(self, error_str):
    self.w.signal.updateLabel(error_str)
    self.w.isRunning = False

    return False

  def run(self):
    self.classificate()

  # 분류
  def classificate(self):
    
    print("SHP파일 읽는 중...")
    if self.read_gis_files(self.gis_path):
      return

    print("이미지파일 읽는 중...")
    img_count = self.count_img_files(self.root_path)
    print("이미지 데이터셋 생성...")
    self.make_data_set()
    print("분류폴더 생성...")
    self.make_class_dir()
    print("영역별 이미지 분류...")
    self.classificate_by_area()
    print("분류 이미지 복사...")
    self.copyValidFile()
    print("미분류 이미지 복사...")
    self.copyInvalidFile()
    self.w.signal.updateLabel("분류 작업 끝.")
    self.w.signal.initPb(0, 100)
    print(" ")  
    print("===================================================================================")
    print("분류 작업 끝. 프로그램 종료.")
    print("===================================================================================")

    self.w.isRunning = False

    if self.w.finish:
      sys.exit()

    return


  # SHP/DBF파일이 포함된 폴더의 경로명으로 폴리곤 ID,폴리곤 쌍 저장
  # 오류나면 False 리턴
  def read_SHP(self, shp_path):

    self.w.signal.initPb(0, 0)
    try:
      geoms = gpd.read_file(shp_path, encoding='utf-8')

      with geoms:
        for area_id, polygon in zip(geoms.Name, geoms.geometry):
          if type(area_id) == type(b'0'):
            area_id=str(area_id)
          print("area_id : " + area_id)
          area_path = os.path.join(self.w.save, area_id)
          self.areas.append(Area(polygon, area_id, area_path))

    except FileNotFoundError:
      return self.printException("에러 : 해당 폴더("+shp_path+")에 SHP 파일 셋을 찾을 수 없습니다.")

    except NotADirectoryError :
      return self.printException("에러 : 해당 경로("+shp_path+")가 디렉토리가 아닙니다.")

    except AttributeError:
      return self.printException("에러 : \"Name\" 필드가 SHP 내에 존재하지 않습니다.")

    return True

        
  # SHP/DBF파일이 포함된 폴더를 선택해서 해당 SHP파일의
  # 경로, 파일명을 얻음
  def read_gis_files(self, gis_dir):
    self.w.signal.updateLabel("(1/6) 구역정보 읽는 중...")

    try:
      cur_file_list = os.listdir(gis_dir)

      for file_name in cur_file_list:
        if os.path.isdir(os.path.join(gis_dir, file_name)):
          continue
        else:
          root, file_ext = os.path.splitext(os.path.join(gis_dir, file_name))
          for ext in [".shp", ".SHP"]:
            if file_ext == ext:
              shp_path = os.path.join(gis_dir, file_name)
              
              return self.read_SHP(shp_path)
      
    except FileNotFoundError:
      return self.printException("에러 : 해당 경로("+gis_dir+")를 찾을 수 없습니다.")
    
    except NotADirectoryError :
      return self.printException("에러 : 해당 경로("+gis_dir+")가 디렉토리가 아닙니다.")

  # 지정된 폴더 내 하위 폴더까지 모든 이미지 파일의 경로명을
  # file_paths 리스트에 저장
  def count_img_files(self, start_dir):

    self.w.signal.initPb(0, 0)
    self.w.signal.updateLabel("(2/6) 영상정보 읽는 중...")

    count = 0
    try:
      cur_file_list = os.listdir(start_dir)

      for file_name in cur_file_list:
        if os.path.isdir(os.path.join(start_dir, file_name)):
          count = count + self.count_img_files(os.path.join(start_dir, file_name))
        else:
          root, file_ext = os.path.splitext(os.path.join(start_dir, file_name))
          for ext in [".png", ".jpg", ".JPG", ".PNG"]:
            if file_ext == ext:
              count = count + 1
              self.ext = ext
              self.file_paths.append(os.path.join(start_dir, file_name))

    except FileNotFoundError :
      self.printException("에러 : 해당 경로("+start_dir+")를 찾을 수 없습니다.")
      return -1

    except NotADirectoryError :
      self.printException("에러 : 해당 경로("+start_dir+")가 디렉토리가 아닙니다.")
      return -1

    return count


  # 이미지 파일을 읽어서 리스트에 저장
  def read_img_files(self, start_dir):

    try:
      cur_file_list = os.listdir(start_dir)
      for file_name in cur_file_list:
        if os.path.isdir(os.path.join(start_dir, file_name)):
          self.read_img_files(os.path.join(start_dir, file_name))

        else:
          root, file_ext = os.path.splitext(os.path.join(start_dir, file_name))
          for ext in [".png", ".jpg", ".JPG", ".PNG"]:
            if file_ext == ext:

              self.ext = ext
              self.file_paths.append(os.path.join(start_dir, file_name))
              self.progress_bar.update(1)

    except FileNotFoundError:
      self.printException("에러 : 해당 경로("+start_dir+")를 찾을 수 없습니다.")
    except NotADirectoryError:
      self.printException("에러 : 해당 경로("+start_dir+")가 디렉토리가 아닙니다.")
    return 
  

  # SHP영역에 해당하는 사진 유무 판단 후 에러 출력, 프로그램 종료
  def check_valid_img(self):
    check = False
    for area in self.areas():
        if len(area.datas) > 0:
          check = True

    sys.exit("[경고] 기선 영역에 포함되는 이미지 파일이 없습니다.")   

    return check


  #폴리곤 리스트의 폴리곤 ID로 이미지를 분류할 폴더 만들기
  def make_class_dir(self):
    dir = self.w.save
    for area in self.areas:
      area_dir_name = os.path.join(dir, area.area_id)
      if os.path.exists(area_dir_name)==False:
        os.mkdir(area_dir_name)
    
    invalid_dir_name = os.path.join(dir, "미분류")
    if os.path.exists(invalid_dir_name)==False:
        os.mkdir(invalid_dir_name)

    return True



  #루트 폴더의 모든 하위 폴더내에 존재하는 이미지 파일의 메타데이터를 추출해서
  #분류에 사용할 데이터셋 만들고 영역별로 분류
  def make_data_set(self):

    pbar = tqdm(total=len(self.file_paths), unit=" 파일 수")
    self.w.signal.initPb(0, len(self.file_paths)-1)
    for file_path, index in zip(self.file_paths, range(0, len(self.file_paths))):
      
      self.w.signal.updateLabel("(3/6) 위치정보 추출 중...[전체 파일 수 : " + str(index+1) + "/" + str(len(self.file_paths)) + "]")
      index=index+1
      #file_name = os.path.basename(file_path)
      
      img = PIL.Image.open(file_path)
      meta_data = img._getexif()
      img.close()

      gps_info = meta_data[34853]

      lat, lon = self.degree_to_latlon(gps_info)

      time_info = meta_data[36867]
      tmp_ymd = time_info.split()[0]
      tmp_ymd = tmp_ymd.replace(':', '-')

      data = Data(file_path, lat, lon, tmp_ymd)

      self.datas.append(data)
      pbValue=self.w.pb.value()
      self.w.signal.updatePb(pbValue+1)
      pbar.update(1)

    pbar.close()

    return


  #도,분,초 좌표 정보를 위도, 경도로 변환
  def degree_to_latlon(self, gps_info):
    lat = round((gps_info[2])[0]+float((gps_info[2])[1])/60+float((gps_info[2])[2])/3600, 8)
    lon = round((gps_info[4])[0]+float((gps_info[4])[1])/60+float((gps_info[4])[2])/3600, 8)

    return lat, lon



  # 영역 기준으로 영역 포함 사진 분류
  def classificate_by_area(self):
    index=0
    pbar = tqdm(total=len(self.datas), unit=" 파일 수")
    self.w.signal.initPb(0, len(self.datas)-1)

    for data in self.datas:
      self.w.signal.updateLabel("(4/6) 영상분류 작업 중...[전체 파일 수 : " + str(index+1) + "/" + str(len(self.datas)) + "]")

      for area in self.areas:
        if data.point.within(area.polygon):
          data.set_area_id(area.area_id)
          area.datas.append(data)
          self.valid_data_num=self.valid_data_num+1
      pbValue=self.w.pb.value()
      self.w.signal.updatePb(pbValue+1)
      pbar.update(1)
      index=index+1

    pbar.close()

    return

  # 영역안에 포함되는 이미지 파일 해당영역/날짜 폴더에 복사
  def copyValidFile(self):
    valid_data_ = 1
    
    self.w.signal.initPb(0, self.valid_data_num-1)

    for area in self.areas:
      if len(area.datas) == 0:
        continue

      pbar = tqdm(total=len(area.datas), unit=" 파일 수", desc="[area_id:" + area.area_id + "]")
      
      data_num=1

      for data in area.datas:
        self.w.signal.updateLabel("(5/6) 분류영상 복사 중... [폴더 이름:" + area.area_id + "][파일 수 : " + str(data_num) 
                + "/" + str(len(area.datas))+"][전체 분류 파일 수 : " + str(valid_data_) + "/" + str(self.valid_data_num)+"]")
        valid_data_=valid_data_+1
        date_dir = os.path.join(area.area_dir_path, data.date)
        if os.path.exists(date_dir) == False:
          os.mkdir(date_dir)

        new_file_name = os.path.join(date_dir, str(data_num).zfill(4)+self.ext)
        data.set_new_file_name(new_file_name)

        if os.path.exists(new_file_name)==False:
          shutil.copy2(data.file_path, new_file_name)

          pbValue=self.w.pb.value()
          self.w.signal.updatePb(pbValue+1)
          
          try:
            self.datas.remove(data)
          # 중복 영역에 포함되어 이미 삭제된 경우 
          except ValueError:
            pass
          
          pbar.update(1)
        
        data_num=data_num+1
        
      pbar.close()
    
    return

  # 영역안에 포함되는 이미지 파일 해당영역/날짜 폴더에 복사
  def copyInvalidFile(self):
    
    self.w.signal.initPb(0, len(self.datas))

    pbar = tqdm(total=len(self.datas), unit=" 파일 수")
      
    data_num=1

    for data in self.datas:
      self.w.signal.updateLabel("(6/6) 미분류영상 복사 중... [폴더 이름: 미분류폴더 ][파일 수 : " + str(data_num) 
              + "/" + str(len(self.datas))+"]")
      date_dir = os.path.join(self.w.save, "미분류", data.date)
      if os.path.exists(date_dir) == False:
        os.mkdir(date_dir)

      new_file_name = os.path.join(date_dir, str(data_num).zfill(4)+self.ext)
      data.set_new_file_name(new_file_name)

      if os.path.exists(new_file_name)==False:
        shutil.copy2(data.file_path, new_file_name)

        pbValue=self.w.pb.value()
        self.w.signal.updatePb(pbValue+1)
        pbar.update(1)
      
      data_num=data_num+1

    pbar.close()
    
    return

class PbSignal(QObject):
    sigInitPb = pyqtSignal(int, int)
    sigUpdatePb = pyqtSignal(int)
    sigBtnOn = pyqtSignal()
    sigUpdateLabel = pyqtSignal("PyQt_PyObject")

    def initPb(self, min, max):
        self.sigInitPb.emit(min, max)

    def updatePb(self, value):
        self.sigUpdatePb.emit(value)

    def runBtnOn(self):
        self.sigBtnOn.emit()

    def updateLabel(self, task):
        self.sigUpdateLabel.emit(task)

#UI파일 연결
#단, UI파일은 Python 코드 파일과 같은 디렉토리에 위치해야한다.
form_class = uic.loadUiType("photoClassificator.ui")[0]

#화면을 띄우는데 사용되는 Class 선언
class WindowClass(QMainWindow, form_class) :
  def __init__(self) :
    super().__init__()

    self.signal = PbSignal()
    self.signal.sigUpdatePb.connect(self.updatePb)
    self.signal.sigInitPb.connect(self.initPb)
    self.signal.sigBtnOn.connect(self.onRunBtn)
    self.signal.sigUpdateLabel.connect(self.updateLabel)

    self.isRunning=False
    self.finish=False

    self.setupUi(self)

    self.SHPPath.setText("E:/항공사진/SHP_UTF8")
    self.imgPath.setText("E:/항공사진/원본영상")
    self.savePath.setText("E:/항공사진/분류폴더")
    self.save="E:/항공사진/분류폴더"
    self.findSHPPathBtn.clicked.connect(self.findSHPPath)
    self.findImgPathBtn.clicked.connect(self.findImgPath)
    self.findSavePathBtn.clicked.connect(self.findSavePath)
    self.executeBtn.clicked.connect(self.execute)
    self.checkBox.stateChanged.connect(self.check)
    #self.SHPPath.setText(SHP)

    self.setFixedSize(670,200)

    #self.save = None
    self.p = None

    self.pb.valueChanged.connect(self.printPercent)

  def check(self):
    if self.checkBox.isChecked():
      self.finish=True
    else:
      self.finish=False

  def updateLabel(self, task):
    self.taskLabel.setText(task)

  def onRunBtn(self):
    self.isRunning = False

  def updatePb(self, value):
    self.pb.setValue(value)

  def initPb(self, min, max):
    self.pb.setValue(0)
    self.pb.setMinimum(min)
    self.pb.setMaximum(max)

  def printPercent(self):
    return

  def findSHPPath(self) :
    fname = QFileDialog.getExistingDirectory(self, 'Open Folder', '')
    if fname:
      self.SHPPath.setText(fname)

    return

  def findImgPath(self) :
    fname = QFileDialog.getExistingDirectory(self, 'Open Folder', '')
    if fname:
      self.imgPath.setText(fname)
    return

  def findSavePath(self) :
    fname = QFileDialog.getExistingDirectory(self, 'Open Folder', '')
    if fname:
      self.savePath.setText(fname)
      self.save=fname
    return


  def execute(self) :
    if self.isRunning==False:
      self.isRunning=True
      self.p = PhotoClassificator(self.imgPath.text(), self.SHPPath.text(), self)
      self.p.start()


# set conf
#f = open("SHPPath.conf", 'r')
#lines = f.readlines()
SHP = "test"
#f.close()

if __name__ == "__main__" :


    #QApplication : 프로그램을 실행시켜주는 클래스
    app = QApplication(sys.argv) 

    #WindowClass의 인스턴스 생성
    myWindow = WindowClass() 

    #프로그램 화면을 보여주는 코드
    myWindow.show()

    #프로그램을 이벤트루프로 진입시키는(프로그램을 작동시키는) 코드
    app.exec_()