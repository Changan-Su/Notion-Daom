import requests

# 你的 Notion API Token
NOTION_API_KEY = "YOUR API KEY"

# 请求头
headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_all_databases():
    """ 搜索 Notion 工作区中的所有数据库，并返回数据库名称和 ID """
    url = "https://api.notion.com/v1/search"
    data = {
        "query": "",
        "filter": {"value": "database", "property": "object"},
        "sort": {"direction": "descending", "timestamp": "last_edited_time"}
    }
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        databases = response.json().get("results", [])
        for db in databases:
            db_id = db["id"]
            db_name = db["title"][0]["text"]["content"] if db["title"] else "无标题"
            print(f"📁 数据库名称: {db_name} | 🆔 ID: {db_id}")
    else:
        print(f"❌ 获取数据库列表失败: {response.text}")

# 运行获取所有数据库 ID
get_all_databases()
