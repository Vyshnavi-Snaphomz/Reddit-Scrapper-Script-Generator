import numpy as np
from db import db
from generate_embeddings import generate_embedding
from load_features import main as load_features

FEATURES_COLL = db["features"]
ISSUES_COLL = db["issues"]
MATCHES_COLL = db["matches"]

def _cosine_sim(a, b):
    """Compute cosine similarity between two vectors"""
    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(b)
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return float(np.dot(a, b) / (a_norm * b_norm))

def match_issues_to_features(threshold=0.75):
    """
    Batch match all issues in ISSUES_COLL to features in FEATURES_COLL.
    Stores matches in MATCHES_COLL with cosine similarity above threshold.
    """
    # Ensure features are loaded
    if FEATURES_COLL.count_documents({}) == 0:
        print("No features found. Loading features first...")
        load_features()

    issues = list(ISSUES_COLL.find({}))
    features = list(FEATURES_COLL.find({}))

    if not issues:
        print("No issues found in DB.")
        return
    if not features:
        print("No features found in DB.")
        return

    print(f"Matching {len(issues)} issues to {len(features)} features...")

    for issue in issues:
        issue_text = issue.get("text")
        if not issue_text or len(issue_text.strip()) < 5:
            continue

        best_match = None
        best_score = 0.0

        for feature in features:
            feature_emb = feature.get("embedding")
            if not feature_emb:
                continue

            # Generate embedding for issue if missing
            issue_emb = issue.get("embedding")
            if not issue_emb:
                issue_emb = generate_embedding(issue_text)
                if issue_emb:
                    ISSUES_COLL.update_one(
                        {"_id": issue["_id"]},
                        {"$set": {"embedding": issue_emb}}
                    )
                else:
                    continue

            score = _cosine_sim(issue_emb, feature_emb)
            if score > best_score:
                best_score = score
                best_match = feature

        if best_match and best_score >= threshold:
            MATCHES_COLL.update_one(
                {"issue_id": issue["_id"]},
                {"$set": {
                    "feature_id": best_match["_id"],
                    "score": best_score,
                    "feature_role": best_match.get("role") 
                }},
                upsert=True
            )
            print(f"Issue: '{issue_text[:50]}...' matched with Feature: '{best_match['text'][:50]}...' (score: {best_score:.2f})")
        else:
            print(f"Issue: '{issue_text[:50]}...' had no match above threshold.")

    print("Issue-feature matching complete.")

def find_top_k_features(text, k=1):
    """
    Given a text, find the top-k features from FEATURES_COLL based on cosine similarity.
    Returns a list of features sorted by score (descending).
    """
    features = list(FEATURES_COLL.find({}))
    if not features:
        print("No features in DB. Loading features...")
        load_features()
        features = list(FEATURES_COLL.find({}))
        if not features:
            return []

    text_emb = generate_embedding(text)
    if not text_emb:
        return []

    scored_features = []
    for feature in features:
        feature_emb = feature.get("embedding")
        if not feature_emb:
            continue
        score = _cosine_sim(text_emb, feature_emb)
        scored_features.append((feature, score))

    # Sort descending by score
    scored_features.sort(key=lambda x: x[1], reverse=True)
    top_features = [f for f, s in scored_features[:k]]
    return top_features

if __name__ == "__main__":
    match_issues_to_features()
