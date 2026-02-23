from sentence_transformers import SentenceTransformer
from db import posts_collection
from tqdm import tqdm

model = SentenceTransformer("all-MiniLM-L6-v2")

def generate_embedding(text):
    if not text or text.strip() == "":
        return None
    return model.encode(text).tolist() 

def embed_posts_and_comments():
    """Generate embeddings for posts and comments"""
    posts = posts_collection.find({})

    for post in tqdm(posts, desc="Embedding posts"):
        post_text = f"{post.get('title', '')}\n\n{post.get('selftext', '')}"
        post_embedding = generate_embedding(post_text)

        if post_embedding:
            posts_collection.update_one(
                {"id": post["id"]},
                {"$set": {"embedding": post_embedding}}
            )

        # Process each comment
        comments = post.get("comments", [])
        for comment in comments:
            comment_text = comment.get("body", "")
            comment_embedding = generate_embedding(comment_text)

            if comment_embedding:
                posts_collection.update_one(
                    {"id": post["id"], "comments.id": comment["id"]},
                    {"$set": {"comments.$.embedding": comment_embedding}}
                )

# if __name__ == "__main__":
#     embed_posts_and_comments()
