
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QGridLayout, QWidget, QComboBox, QLabel
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtCore import Qt


class RouletteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Рулетка")
        self.setGeometry(100, 100, 500, 500)

        # Основное окно
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)

        # Лейаут для кнопок
        layout = QGridLayout()
        self.main_widget.setLayout(layout)
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QGridLayout, QWidget, QComboBox, QLabel
from PyQt5.QtGui import QPixmap, QColor
from PyQt5.QtCore import Qt

class RouletteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Рулетка")
        self.setGeometry(100, 100, 600, 500)

        # Основное окно
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)

        # Лейаут для кнопок
        layout = QGridLayout()
        self.main_widget.setLayout(layout)

        # Список номеров рулетки
        self.numbers = [
            0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26
        ]

        # Список чисел, которые будут красными
        self.red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

        # Список для колонок
        self.columns = {1: [1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34], 
                        2: [2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35], 
                        3: [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36]}

        # Создание кнопок для номеров
        self.buttons = {}
        for i, number in enumerate(self.numbers):
            button = QPushButton(str(number), self)
            button.setFixedSize(50, 50)

            # Определение красных и черных чисел
            if number in self.red_numbers:
                button.setStyleSheet("background-color: red; color: white; border: 2px solid white;")
            elif number == 0:
                button.setStyleSheet("background-color: green; color: white; border: 2px solid white;")
            else:
                button.setStyleSheet("background-color: black; color: white; border: 2px solid white;")

            button.clicked.connect(self.on_number_click)
            layout.addWidget(button, i // 12, i % 12)
            self.buttons[number] = button

        # Добавление колонок
        self.add_column_labels(layout)

        # Номинал выбора
        self.nominal_selector = QComboBox(self)
        self.nominal_selector.addItem("1")
        self.nominal_selector.addItem("5")
        self.nominal_selector.addItem("10")
        self.nominal_selector.addItem("25")
        self.nominal_selector.addItem("50")
        self.nominal_selector.setFixedWidth(100)
        layout.addWidget(self.nominal_selector, 3, 13, 1, 1)

        # Лейбл для отображения выбранного числа
        self.selected_number_label = QLabel("Выберите число и номинал", self)
        layout.addWidget(self.selected_number_label, 4, 0, 1, 14)

    def add_column_labels(self, layout):
        # Добавление названий для колонок
        column_labels = ['1-я колонка', '2-я колонка', '3-я колонка']
        for col_index, label in enumerate(column_labels, 1):
            column_label = QLabel(label, self)
            layout.addWidget(column_label, 0, 12 + col_index)

    def on_number_click(self):
        # Получаем номер, на который кликнул пользователь
        sender = self.sender()
        number = int(sender.text())

        # Получаем выбранный номинал
        nominal = int(self.nominal_selector.currentText())

        # Отображаем выбранное число и номинал
        self.selected_number_label.setText(f"Вы выбрали число {number} с номиналом {nominal}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RouletteWindow()
    window.show()
    sys.exit(app.exec_())
