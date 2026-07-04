import csv

# 读取原始数据
with open('mock_data_weekly_dimension_full.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    rows = list(reader)

# 删除"异动标签"列（最后一列）
header = rows[0]
new_header = header[:-1]  # 删除最后一列

new_rows = [new_header]
for row in rows[1:]:
    new_row = row[:-1]  # 删除最后一列
    new_rows.append(new_row)

# 写入新文件
with open('mock_data_weekly_dimension_full_clean.csv', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerows(new_rows)

print(f"已清理数据文件，删除了'异动标签'列")
print(f"原始行数: {len(rows)}")
print(f"清理后行数: {len(new_rows)}")
print(f"原始列数: {len(header)}")
print(f"清理后列数: {len(new_header)}")