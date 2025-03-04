from flask import Flask, request, jsonify
import requests
import json
import time

app = Flask(__name__)

# ========== Notion 配置 ==========
NOTION_API_KEY = "YOU KEY"
MAPPING_DATABASE_ID = "MAPPING ID"  # 请替换为实际 Button Mapping 数据库ID
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

@app.route("/notion-webhook", methods=["POST"])
def notion_webhook():
    """
    Webhook 入口：
      - 从 Webhook 数据中获取 A 页面 ID 以及 properties
      - 读取 Button Mapping 数据库中的映射数据，每行包含：
            * Name：关键词（如 "%Fiary", "%Collection"）
            * Relation：A 页面中用于关联 B 页面的属性名称（如 "Fiarybase", "Collection Home"）
      - 对于每个映射，只有当 A 页面的 properties 中存在对应 Relation 且关联数据不为空时才处理：
            * 从 webhook payload 的 properties 中获取 B 页面 ID 列表
            * 在 A 页面中查找 marker 后的同步块（如果存在则返回该同步块 ID；如果 marker 存在但后面没有同步块，则尝试在页面底部创建新的同步块；如果页面中完全没有 marker，则跳过）
            * 将该同步块复制到所有对应的 B 页面中
    """
    data = request.json
    print(f"✅ 收到 Notion Webhook 请求: {json.dumps(data, indent=2)}")

    source_page_id = data.get("data", {}).get("id")
    if not source_page_id:
        return jsonify({"error": "未找到 A 页面 ID"}), 400

    # 从 webhook payload 中获取 A 页面的 properties
    source_props = data.get("data", {}).get("properties", {})

    # 读取 Button Mapping 数据库（使用 API 查询）
    mapping_rows = get_button_mapping_rows(MAPPING_DATABASE_ID)
    if not mapping_rows:
        return jsonify({"error": "Button Mapping 数据库为空"}), 400

    for mapping in mapping_rows:
        marker = mapping["Name"]         # 如 "%Fiary" 或 "%Collection"
        relation_prop = mapping["Relation"] # 如 "Fiarybase" 或 "Collection Home"
        print(f"=== 处理映射：关键词: {marker}, Relation: {relation_prop} ===")

        # 仅使用 webhook payload 中的数据来判断是否触发该映射
        b_page_ids = get_b_pages_from_property_from_webhook(source_props, relation_prop)
        if not b_page_ids:
            print(f"⚠️ Webhook中 A 页面属性 {relation_prop} 无关联 B 页面，跳过")
            continue

        # 查找 A 页面中 marker 后的同步块
        sync_block_id = find_synced_block_after_marker(source_page_id, marker)
        if sync_block_id == "marker_not_found":
            print(f"⚠️ A 页面中完全未找到 marker {marker}，跳过此映射")
            continue
        if not sync_block_id:
            print(f"⚠️ 找到 marker {marker} 但后面无同步块，尝试在页面底部创建新的同步块...")
            sync_block_id = create_synced_block_at_bottom(source_page_id, marker)
            if not sync_block_id:
                print("❌ 创建同步块失败，跳过此映射")
                continue

        for b_page_id in b_page_ids:
            print(f"🚀 将 A 页面同步块 {sync_block_id} 复制到 B 页面 {b_page_id}")
            copy_synced_block_content(sync_block_id, b_page_id)

    return jsonify({"status": "success"})

# ========== 读取 Button Mapping 数据库 ==========
def get_button_mapping_rows(database_id):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    resp = requests.post(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"❌ 读取 Button Mapping 失败: {resp.text}")
        return []
    results = resp.json().get("results", [])
    rows = []
    for row in results:
        props = row.get("properties", {})
        name_val = extract_plain_text(props.get("Name", {}))
        relation_val = extract_plain_text(props.get("Relation", {}))
        if name_val and relation_val:
            rows.append({"Name": name_val, "Relation": relation_val})
    print(f"✅ 读取到 {len(rows)} 行 Button Mapping 数据: {rows}")
    return rows

def extract_plain_text(prop):
    ptype = prop.get("type")
    if ptype == "title":
        return "".join(t.get("plain_text", "") for t in prop.get("title", []))
    elif ptype == "rich_text":
        return "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
    return ""

# ========== 从 webhook payload 获取 B 页面 ID ==========
def get_b_pages_from_property_from_webhook(source_props, property_name):
    """
    从 webhook payload 中的 A 页面 properties 获取指定 Relation 的 B 页面 ID 列表
    """
    if property_name not in source_props:
        print(f"⚠️ Webhook中未包含属性 {property_name}")
        return []
    rel_prop = source_props[property_name]
    if rel_prop.get("type") != "relation":
        print(f"⚠️ Webhook中属性 {property_name} 不是 relation 类型")
        return []
    relation_list = rel_prop.get("relation", [])
    if not relation_list:
        print(f"⚠️ Webhook中属性 {property_name} 关联列表为空")
        return []
    b_page_ids = [r["id"] for r in relation_list]
    print(f"✅ Webhook: A 页面属性 {property_name} -> B 页面列表: {b_page_ids}")
    return b_page_ids

# ========== 获取页面 Blocks ==========
def get_page_blocks(page_id):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return resp.json().get("results", [])
    print(f"❌ 获取页面 {page_id} Blocks 失败: {resp.text}")
    return []

# ========== 查找同步块 ==========
def find_synced_block_after_marker(page_id, marker):
    """
    在 A 页面中查找指定 marker 后面的第一个同步块。
    如果页面中完全没有 marker，则返回 "marker_not_found"；
    如果 marker 存在但 marker 后没有同步块，则返回 None。
    """
    print(f"🔍 获取 A 页面 {page_id} 的 Blocks...")
    blocks = get_page_blocks(page_id)
    if not blocks:
        return None
    marker_found = False
    for i, block in enumerate(blocks):
        btype = block.get("type")
        text_content = block.get(btype, {}).get("rich_text", [])
        if text_content and text_content[0].get("text", {}).get("content") == marker:
            marker_found = True
            print(f"✅ 找到 marker {marker} in {btype}，位置 {i}")
            # 检查 marker 后的第一个 block是否为同步块
            if i + 1 < len(blocks):
                next_block = blocks[i+1]
                if next_block.get("type") == "synced_block":
                    print(f"✅ Marker 后的第一个 block已为同步块，ID: {next_block.get('id')}")
                    return next_block.get("id")
            return None
    if not marker_found:
        print(f"⚠️ 未找到 marker {marker} in A 页面 {page_id}")
        return "marker_not_found"
    return None

# ========== 创建同步块（追加到页面底部） ==========
def create_synced_block_at_bottom(page_id, marker):
    """
    在 A 页面底部创建新的同步块（追加到页面末尾），返回同步块ID。
    仅在页面中存在 marker 的情况下调用。
    """
    new_sync_block = {
        "object": "block",
        "type": "synced_block",
        "synced_block": {"synced_from": None}
    }
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    resp = requests.patch(url, headers=HEADERS, json={"children": [new_sync_block]})
    if resp.status_code == 200:
        print(f"✅ 在 A 页面底部新建同步块成功")
        time.sleep(1)
        result = find_synced_block_after_marker(page_id, marker)
        if result == "marker_not_found":
            return None
        return result or new_sync_block.get("id")
    else:
        print(f"❌ 创建同步块失败: {resp.text}")
        return None

# ========== 同步到 B 页面 ==========
def copy_synced_block_content(sync_block_id, target_page_id):
    """
    将 A 页面的同步块复制到 B 页面：
      - 若同步块已同步自其他块，则使用原始块 ID；否则使用当前同步块 ID。
      - 在 B 页面追加一个新的同步块引用原始块。
    """
    detail_url = f"https://api.notion.com/v1/blocks/{sync_block_id}"
    detail_resp = requests.get(detail_url, headers=HEADERS)
    if detail_resp.status_code != 200:
        print(f"❌ 获取源同步块详情失败: {detail_resp.text}")
        return
    source_block = detail_resp.json()
    synced_info = source_block.get("synced_block", {})
    if synced_info.get("synced_from"):
        original_block_id = synced_info["synced_from"].get("block_id")
        print(f"✅ 源同步块 {sync_block_id} 同步自 {original_block_id}")
    else:
        original_block_id = sync_block_id

    new_sync_block = {
        "object": "block",
        "type": "synced_block",
        "synced_block": {"synced_from": {"block_id": original_block_id}}
    }
    add_url = f"https://api.notion.com/v1/blocks/{target_page_id}/children"
    resp = requests.patch(add_url, headers=HEADERS, json={"children": [new_sync_block]})
    if resp.status_code == 200:
        print(f"✅ 成功同步 block 到 B 页面 {target_page_id}")
    else:
        print(f"❌ 同步 block 失败: {resp.text}")

# ========== 备用方案：从 Notion API 获取 A 页面关联的 B 页面 ID ==========
def get_related_page_ids_from_notion(page_id):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"❌ 获取 A 页面失败: {resp.text}")
        return None
    props = resp.json().get("properties", {})
    relation_prop = props.get("Fiarybase", {})
    relation_list = relation_prop.get("relation", [])
    if relation_list:
        related_page_ids = [r["id"] for r in relation_list]
        print(f"✅ 从 Notion API 获取 `Fiarybase` 关联页面: {related_page_ids}")
        return related_page_ids
    else:
        print(f"⚠️ A 页面 {page_id} 没有关联的 B 页面")
        return None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
