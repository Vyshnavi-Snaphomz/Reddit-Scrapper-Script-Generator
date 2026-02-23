import os
import yaml
from datetime import datetime
from tqdm import tqdm
from db import db
from generate_embeddings import generate_embedding 

FEATURES_FILE = os.path.join("KnowledgeBase", "feature.yaml")
FEATURES_COLL = db["features"]

def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def flatten_features(yaml_data):
    """
    Flatten seller and buyer features into a list of dicts with text blocks.
    Works with your Snaphomz_Features YAML structure.
    """
    all_features = []
    top = yaml_data.get("Snaphomz_Features", {})

    for role_key in ["Seller_Features", "Buyer_Features"]:
        features = top.get(role_key, [])
        for f in features:
            # combine description + justification + risk + mitigation
            description = f.get("Description") or ""
            justification = f.get("Justification") or ""
            risk = f.get("Risk") or ""
            mitigation = f.get("Mitigation") or ""
            
            combined_text = " ".join(filter(None, [
                description.strip(),
                justification.strip(),
                risk.strip(),
                mitigation.strip()
            ]))

            if combined_text:
                all_features.append({
                    "text": combined_text,
                    "role": "seller" if role_key == "Seller_Features" else "buyer"
                })
    return all_features

def main():
    if not os.path.exists(FEATURES_FILE):
        print(f"{FEATURES_FILE} not found")
        return

    yaml_data = load_yaml(FEATURES_FILE)
    features = flatten_features(yaml_data)
    print(f"Processing {len(features)} features from YAML")

    for f in tqdm(features, desc="Embedding features"):
        block = f["text"]
        ftype = f["role"]

        if len(block) < 10:
            continue

        # skip if already in DB (text + role)
        if FEATURES_COLL.find_one({"text": block, "role": ftype}):
            continue

        emb = generate_embedding(block)
        if not emb:
            continue

        doc = {
            "text": block,
            "role": ftype,
            "source_file": FEATURES_FILE,
            "embedding": emb,
            "created_at": datetime.utcnow()
        }
        FEATURES_COLL.insert_one(doc)

    print("Done. Features collection has", FEATURES_COLL.count_documents({}))

if __name__ == "__main__":
    main()


