from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QTableWidget, QTableWidgetItem


class HeaderInfoDialog(QDialog):
    def __init__(self, header_info, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(file_name)

        # header_data = {"Attribute": [], "Value": []}
        # # Extract attributes and values
        # for attr_name in dir(header_info):
        #     if not attr_name.startswith("_"):
        #         attr_value = getattr(header_info, attr_name)
        #         header_data["Attribute"].append(attr_name)
        #         header_data["Value"].append(attr_value)
        # layout = QVBoxLayout()
        # self.table_widget = QTableWidget()
        # self.table_widget.setRowCount(len(header_data["Attribute"]))
        # self.table_widget.setColumnCount(2)
        # for i, (attr, value) in enumerate(zip(header_data["Attribute"], header_data["Value"])):
        #     attr_item = QTableWidgetItem(attr)
        #     value_item = QTableWidgetItem(str(value))
        #     self.table_widget.setItem(i, 0, attr_item)
        #     self.table_widget.setItem(i, 1, value_item)
        # layout.addWidget(self.table_widget)
        # close_button = QPushButton("Close")
        # close_button.clicked.connect(self.close)
        # layout.addWidget(close_button)
        # self.setLayout(layout)

        layout = QVBoxLayout()

        self.header_textedit = QTextEdit()
        self.header_textedit.setPlainText(str(header_info))
        self.header_textedit.setReadOnly(True)

        layout.addWidget(self.header_textedit)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        layout.addWidget(close_button)

        self.setLayout(layout)

