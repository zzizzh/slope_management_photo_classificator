import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

class PbSignal(QObject):
    signal = pyqtSignal()

    def run(self):
        self.signal.emit()

class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        mysignal = PbSignal()
        mysignal.signal.connect(self.signal_emitted)
        mysignal.run()

    @pyqtSlot()
    def signal_emitted(self):
        print("signal1 emitted")


app = QApplication(sys.argv)
window = MyWindow()
window.show()
app.exec_()