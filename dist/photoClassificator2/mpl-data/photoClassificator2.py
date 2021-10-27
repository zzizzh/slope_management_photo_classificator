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
from shapely.geometry import Point, Polygon
from tqdm import tqdm

class Data:
	def __init__(self, file_path, lat, lon, date):
		self.new_file_path = None						## 새로 복사할 경로명
		self.file_path = file_path						## 경로명
		self.point = Point(lon, lat)					## 위도, 경도 포인트
		self.area_id = None								## 해당 폴리곤 ID
		self.date = date

	def is_valid(self):
		if self.area_id != None:
			return True
		return False

	def set_area_id(self, area_id):
		self.area_id = area_id

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

		self.areas = []        			# SHP에서 추출한 블록 ID, 해당 블록 내의 폴리곤 리스트 쌍
		self.file_paths = []				# 이미지 경로명 리스트
		self.datas = []						# 이미지 파일에서 추출한 메타데이터로 생성한 이미지파일명, 데이터 객체 쌍
		self.w = widget
		self.valid_data_num=0

	def run(self):
		self.classificate()

	# 분류
	def classificate(self):
		
		print("reading SHP file...")
		self.w.signal.updateLabel("(1/6) reading SHP file...")
		self.read_gis_files(self.gis_path)
		print("reading img file...")
		self.w.signal.updateLabel("(2/6) reading img file...")
		img_count = self.count_img_files(self.root_path)
		self.progress_bar = tqdm(total=img_count, unit=" 파일 수")
		self.read_img_files(self.root_path)
		self.progress_bar.close()
		print("create img data set...")
		self.make_data_set()
		print("create class dir...")
		self.make_class_dir()
		print("classficate by area...")
		self.classificate_by_area()
		print("copy img file...")
		self.copyValidFile()

		print(" ")	
		print("===================================================================================")
		print("분류 작업 끝. 프로그램 종료.")
		print("===================================================================================")

		if self.w.finish:
			sys.exit()

		return


	# SHP/DBF파일이 포함된 폴더의 경로명으로 폴리곤 ID,폴리곤 쌍 저장
	def read_SHP(self, shp_path):

		geoms = gpd.read_file(shp_path)

		for area_id, polygon in zip(geoms.ID, geoms.geometry):
			area_path = os.path.join(self.w.save, area_id)
			self.areas.append(Area(polygon, area_id, area_path))

		return

				
	# SHP/DBF파일이 포함된 폴더를 선택해서 해당 SHP파일의
	# 경로, 파일명을 얻음
	def read_gis_files(self, gis_dir):
		cur_file_list = os.listdir(gis_dir)

		for file_name in cur_file_list:
			if os.path.isdir(os.path.join(gis_dir, file_name)):
				continue
			else:
				root, file_ext = os.path.splitext(os.path.join(gis_dir, file_name))
				for ext in [".shp", ".SHP"]:
					if file_ext == ext:
						shp_path = os.path.join(gis_dir, file_name)
						self.read_SHP(shp_path)
						return
			
		
		sys.exit("[에러] SHP 파일 셋을 찾을 수 없습니다.")     


	# 지정된 폴더 내 하위 폴더까지 모든 이미지 파일의 경로명을
	# file_paths 리스트에 저장
	def count_img_files(self, start_dir):
		count = 0

		cur_file_list = os.listdir(start_dir)

		for file_name in cur_file_list:
			if os.path.isdir(os.path.join(start_dir, file_name)):
				count = count + self.count_img_files(os.path.join(start_dir, file_name))
			else:
				root, file_ext = os.path.splitext(os.path.join(start_dir, file_name))
				for ext in [".png", ".jpg", ".JPG", ".PNG"]:
					if file_ext == ext:
						count = count + 1

		return count


	# 이미지 파일을 읽어서 리스트에 저장
	def read_img_files(self, start_dir):

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

		if len(self.file_paths) == 0:
			sys.exit("[에러] 이미지 파일을 찾을 수 없습니다.")

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

		return



	#루트 폴더의 모든 하위 폴더내에 존재하는 이미지 파일의 메타데이터를 추출해서
	#분류에 사용할 데이터셋 만들고 영역별로 분류
	def make_data_set(self):

		pbar = tqdm(total=len(self.file_paths), unit=" 파일 수")
		self.w.signal.initPb(0, len(self.file_paths)-1)
		for file_path, index in zip(self.file_paths, range(0, len(self.file_paths))):
			
			self.w.signal.updateLabel("(3/6) 이미지 데이터 추출 중...[전체 파일 수 : " + str(index+1) + "/" + str(len(self.file_paths)) + "]")
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
			self.w.signal.updateLabel("(4/6) 이미지 영역 분류 작업 중...[전체 파일 수 : " + str(index+1) + "/" + str(len(self.datas)) + "]")

			for area in self.areas:
				if data.point.within(area.polygon):
					data.area_id=area.area_id
					area.datas.append(data)
					self.valid_data_num=self.valid_data_num+1
			pbValue=self.w.pb.value()
			self.w.signal.updatePb(pbValue+1)
			pbar.update(1)
			index=index+1

		pbar.close()

		return


	def copyValidFile(self):
		valid_data_ = 1
		
		self.w.signal.initPb(0, self.valid_data_num-1)

		for area in self.areas:
			if len(area.datas) == 0:
				continue

			pbar = tqdm(total=len(area.datas), unit=" 파일 수", desc="[area_id:" + area.area_id + "]")
			
			data_num=1

			for data in area.datas:
				self.w.signal.updateLabel("(6/6) 분류 이미지 복사 중... [폴더 이름:" + area.area_id + "][파일 수 : " + str(data_num) 
							  + "/" + str(len(area.datas))+"][전체 분류 파일 수 : " + str(valid_data_) + "/" + str(self.valid_data_num)+"]")
				valid_data_=valid_data_+1
				data_num=data_num+1
				date_dir = os.path.join(area.area_dir_path, data.date)
				if os.path.exists(date_dir) == False:
					os.mkdir(date_dir)

				new_file_name = os.path.join(date_dir, os.path.basename(data.file_path)+self.ext)
				data.set_new_file_name(new_file_name)

				if os.path.exists(new_file_name)==False:
					shutil.copy2(data.file_path, new_file_name)

					pbValue=self.w.pb.value()
					self.w.signal.updatePb(pbValue+1)
					pbar.update(1)
				
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

		self.SHPPath.setText("E:/sample/shp")
		self.imgPath.setText("E:/sample/01 항공사진")
		self.savePath.setText("E:/sample/새 폴더")
		self.save="E:/sample/새 폴더"
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