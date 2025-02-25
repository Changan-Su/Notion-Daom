import requests
import time

# Notion API 配置
NOTION_API_KEY = "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"
SOURCE_DATABASE_ID = "1a4f3c4a-351e-805a-9aaa-ec6f0dc28e69"
TARGET_DATABASE_ID = "1a4f3c4a-351e-804e-a50f-e5d407c8255e"


headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 映射源数据库和目标数据库的字段
properties_map = {
    "Name": "Name",
    "Multi-select": "slect",   # 源数据库 `n1` 对应目标数据库 `n2`
    "Date 1": "Date",  # `date` 对应 `created_at`
    "Value 1": "V"  # `status` 对应 `progress`
}

def get_page_content(page_id):
    """ 获取 Notion 页面 Block 内容 """
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json().get("results", [])  # ✅ 确保返回 Block 列表
    else:
        print(f"❌ 获取页面内容失败: {response.text}")
        return []


# 获取数据库中的所有页面
def get_database_pages(database_id):
    """ 获取数据库中的所有页面 """
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    response = requests.post(url, headers=headers)

    if response.status_code == 200:
        return response.json().get("results", [])
    else:
        print(f"❌ 获取数据库数据失败: {response.text}")
        return []

# 获取页面的内容
def get_database_properties(database_id):
    """ 获取目标数据库的字段列表 """
    url = f"https://api.notion.com/v1/databases/{database_id}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        properties = response.json().get("properties", {})
        return list(properties.keys())  # 返回字段名称列表
    else:
        print(f"❌ 无法获取目标数据库属性: {response.text}")
        return []


# 复制页面到目标数据库
def copy_page(source_page, target_database_id):
    """ 复制页面到目标数据库，使用属性映射 """
    properties = source_page.get("properties", {})

    if not properties:
        print(f"⚠️ 页面 {source_page['id']} 没有 properties，跳过复制")
        return None

    # 获取目标数据库的字段列表
    target_properties = get_database_properties(target_database_id)

    valid_properties = {}
    for key, value in properties.items():
        # ✅ 仅复制 `properties_map` 里定义的字段，并且目标数据库存在该字段
        if key in properties_map and properties_map[key] in target_properties:
            new_key = properties_map[key]  # 目标数据库的字段名称
            prop_type = value["type"]  # 获取源数据库字段类型
            
            # 处理不同类型的数据，确保格式正确
            if prop_type == "title":
                valid_properties[new_key] = {"title": value["title"]}
            elif prop_type == "rich_text":
                valid_properties[new_key] = {"rich_text": value["rich_text"]}
            elif prop_type == "number":
                valid_properties[new_key] = {"number": value["number"]}
            elif prop_type == "select":
                valid_properties[new_key] = {"select": value["select"]}
            elif prop_type == "multi_select":
                valid_properties[new_key] = {"multi_select": value["multi_select"]}
            elif prop_type == "date":
                valid_properties[new_key] = {"date": value["date"]}
            elif prop_type == "checkbox":
                valid_properties[new_key] = {"checkbox": value["checkbox"]}
            elif prop_type == "email":
                valid_properties[new_key] = {"email": value["email"]}
            elif prop_type == "phone_number":
                valid_properties[new_key] = {"phone_number": value["phone_number"]}
            elif prop_type == "url":
                valid_properties[new_key] = {"url": value["url"]}
            else:
                print(f"⚠️ 无法处理字段类型: {key} ({prop_type})，跳过")
        else:
            print(f"⚠️ 忽略字段: {key} -> 无映射或目标数据库无对应字段")

    # 确保 `valid_properties` 不为空，否则跳过复制
    if not valid_properties:
        print(f"⚠️ 页面 {source_page['id']} 没有可复制的 properties，跳过")
        return None

    # 创建新页面数据
    new_page_data = {
        "parent": {"database_id": target_database_id},
        "properties": valid_properties
    }

    url = "https://api.notion.com/v1/pages"
    response = requests.post(url, json=new_page_data, headers=headers)

    if response.status_code == 200:
        new_page_id = response.json()["id"]
        print(f"✅ 页面复制成功: {new_page_id}")
        return new_page_id
    else:
        print(f"❌ 页面复制失败: {response.text}")
        return None

# 复制 Notion 数据库中的所有页面
def copy_database(source_database_id, target_database_id):
    pages = get_database_pages(source_database_id)
    
    for page in pages:
        page_id = page["id"]
        print(f"正在复制页面: {page_id}")

        new_page_id = copy_page(page, target_database_id)

        if new_page_id:
            content = get_page_content(page_id)
            for block in content:
                copy_block(new_page_id, block)

        time.sleep(1)  # 避免 Notion API 速率限制

# 复制 Block
def copy_block(page_id, block):
    """ 复制 Notion 页面 Block 内容 """
    if not isinstance(block, dict) or "type" not in block:
        print(f"⚠️ 无效的 block 数据，跳过: {block}")
        return
    
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"

    block_type = block["type"]
    if block_type not in block:
        print(f"⚠️ 无法复制 block: {block}")
        return

    new_block = {
        "children": [{
            "object": "block",
            "type": block_type,
            block_type: block.get(block_type, {})
        }]
    }

    response = requests.patch(url, json=new_block, headers=headers)

    if response.status_code == 200:
        print(f"✅ Block 复制成功")
    else:
        print(f"❌ Block 复制失败: {response.text}")


# 开始执行
copy_database(SOURCE_DATABASE_ID, TARGET_DATABASE_ID)
