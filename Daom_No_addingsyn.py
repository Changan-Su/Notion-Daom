# 不添加同步块

from flask import Flask, request, jsonify
import requests
import json
import time

# 初始化 Flask 服务器
app = Flask(__name__)

# Notion API 配置
NOTION_API_KEY = "API KEY"
RELATION_PROPERTY_NAME = "Fiarybase"  # Database A 里的 Relation 属性名称
FIARY_MARKER = "%Fiary"  # 用于查找的标记

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

@app.route("/notion-webhook", methods=["POST"])
def notion_webhook():
    """
    Webhook 入口：
    - 从 Webhook 数据中获取 A 页面 ID（触发页面）和 Fiarybase 关联的 B 页面 ID
    - 在 A 页面中查找 `%Fiary` 标记后的同步块
    - 将该同步块复制到每个 B 页面（使用原始同步块作为源，如果已在同步中）
    """
    data = request.json
    print(f"✅ 收到 Notion Webhook 请求: {json.dumps(data, indent=2)}")

    # 获取 A 页面 ID（触发页面）
    source_page_id = data.get("data", {}).get("id")
    if not source_page_id:
        print("❌ 未能获取 A 页面 ID")
        return jsonify({"error": "未找到触发页面 ID"}), 400

    # 从 Webhook 数据中直接获取 Fiarybase 关联的 B 页面 ID
    related_page_ids = get_related_page_ids(data)
    if not related_page_ids:
        return jsonify({"error": "未找到关联的 B 页面"}), 400

    print(f"✅ A 页面 ID: {source_page_id}")
    print(f"✅ 直接从 Webhook 解析关联页面 ID: {related_page_ids}")

    # 在 A 页面中查找 %Fiary 标记后的同步块
    sync_block_id = find_synced_block_after_marker(source_page_id)
    if not sync_block_id:
        print(f"⚠️ A 页面 {source_page_id} 没有 `%Fiary` 后的同步块")
        return jsonify({"error": "未找到同步块"}), 400

    # 将 A 页面的该同步块复制到每个 B 页面
    for target_page_id in related_page_ids:
        print(f"🚀 将 A 页面同步块 {sync_block_id} 复制到 B 页面 {target_page_id}")
        copy_synced_block_content(sync_block_id, target_page_id)

    return jsonify({"status": "success"})

def get_related_page_ids(webhook_data):
    """ 从 Webhook 数据中直接获取 Fiarybase 关联的 B 页面 ID """
    properties = webhook_data.get("data", {}).get("properties", {})
    relation_property = properties.get(RELATION_PROPERTY_NAME, {})
    relation_list = relation_property.get("relation", [])
    if relation_list:
        related_page_ids = [r["id"] for r in relation_list]
        return related_page_ids
    else:
        print("⚠️ Webhook 数据中 `Fiarybase` 为空")
        return None

def get_page_content_with_debug(page_id, retries=3, delay=2):
    """ 获取页面 Blocks，并打印调试信息 """
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    for attempt in range(retries):
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            blocks = response.json().get("results", [])
            print(f"✅ 成功获取页面 {page_id} 的 Blocks，共 {len(blocks)} 个")
            for idx, block in enumerate(blocks):
                print(f"🔍 Block {idx+1}: {json.dumps(block, indent=2, ensure_ascii=False)}\n")
            return blocks
        elif response.status_code == 404:
            print(f"⚠️ 第 {attempt+1}/{retries} 次尝试：页面 {page_id} 未找到，等待 {delay} 秒后重试...")
            time.sleep(delay)
        else:
            print(f"❌ 获取页面 {page_id} 内容失败: {response.text}")
            return None
    print(f"❌ 页面 {page_id} 达到最大重试次数，无法获取 Blocks")
    return None

def find_synced_block_after_marker(source_page_id):
    """ 在 A 页面查找 `%Fiary` 标记后的同步块 """
    print(f"🔍 获取 A 页面 {source_page_id} 的 Blocks...")
    blocks = get_page_content_with_debug(source_page_id)
    if not blocks:
        print(f"❌ 无法获取 A 页面 {source_page_id} 的 Block 数据")
        return None

    found_marker = False
    for block in blocks:
        block_type = block.get("type")
        text_content = block.get(block_type, {}).get("rich_text", [])
        if text_content and text_content[0].get("text", {}).get("content") == FIARY_MARKER:
            found_marker = True
            print(f"✅ 找到 `%Fiary` 标记 in {block_type}")
            continue  # 跳过标记块
        if found_marker and block_type == "synced_block":
            print(f"✅ 找到标记后的同步块 ID: {block.get('id')}")
            return block.get("id")
    print(f"⚠️ A 页面 {source_page_id} 没有 `%Fiary` 后的同步块")
    return None

def copy_synced_block_content(sync_block_id, target_page_id):
    """
    将 A 页面的同步块复制到 B 页面
    如果源同步块已同步自其他块，则获取原始同步块 ID
    """
    # 先获取源同步块详情
    url = f"https://api.notion.com/v1/blocks/{sync_block_id}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ 获取源同步块详情失败: {response.text}")
        return
    source_block = response.json()
    # 如果源同步块已经在同步自其他块，则使用原始块 ID
    synced_info = source_block.get("synced_block", {})
    if synced_info.get("synced_from"):
        original_block_id = synced_info["synced_from"].get("block_id")
        print(f"✅ 源同步块 {sync_block_id} 正在同步自原始块 {original_block_id}")
    else:
        original_block_id = sync_block_id

    # 创建新的同步块在 B 页面，引用原始块
    new_sync_block = {
        "object": "block",
        "type": "synced_block",
        "synced_block": {
            "synced_from": {"block_id": original_block_id}
        }
    }
    add_block_url = f"https://api.notion.com/v1/blocks/{target_page_id}/children"
    response = requests.patch(add_block_url, json={"children": [new_sync_block]}, headers=headers)
    if response.status_code == 200:
        print(f"✅ 成功同步 block 到 B 页面 {target_page_id}")
    else:
        print(f"❌ 复制 block 失败: {response.text}")

def get_related_page_ids_from_notion(page_id):
    """
    从 Notion API 获取 A 页面中 Fiarybase 关联的 B 页面 ID
    （备用方案，如果 Webhook 数据不全则可调用）
    """
    url = f"https://api.notion.com/v1/pages/{page_id}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ 获取 A 页面失败: {response.text}")
        return None
    properties = response.json().get("properties", {})
    relation_property = properties.get(RELATION_PROPERTY_NAME, {})
    relation_list = relation_property.get("relation", [])
    if relation_list:
        related_page_ids = [r["id"] for r in relation_list]
        print(f"✅ 从 Notion API 获取 `Fiarybase` 关联页面: {related_page_ids}")
        return related_page_ids
    else:
        print(f"⚠️ A 页面 {page_id} 没有关联的 B 页面")
        return None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
