import csv

# 处理mock_data_weekly_dimension.csv
with open('mock_data_weekly_dimension.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    rows = list(reader)

# 删除"异动标签"列（最后一列）
header = rows[0]
new_header = header[:-1]

new_rows = [new_header]
for row in rows[1:]:
    new_row = row[:-1]
    new_rows.append(new_row)

# 写入新文件
with open('mock_data_weekly_dimension_clean.csv', 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.writer(f)
    writer.writerows(new_rows)

print(f"已清理 mock_data_weekly_dimension.csv")
print(f"删除了'异动标签'列")
print(f"原始列数: {len(header)}, 清理后列数: {len(new_header)}")