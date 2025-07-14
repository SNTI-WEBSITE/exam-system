from utils.parse_excel import parse_excel_file

# Replace this with your actual Excel file path
file_path = "Book1.xlsx"

questions = parse_excel_file(file_path)
for q in questions:
    print(q)
