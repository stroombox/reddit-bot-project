import React, { useState, useEffect } from "react"

export default function Suggestions() {
  const API = process.env.REACT_APP_API_URL
  const [posts, setPosts] = useState([])

  // 1) Load raw posts on component load
  useEffect(() => {
    fetch(`${API}/suggestions`)
      .then(r => r.json())
      .then(data => setPosts(data))
      .catch(console.error)
  }, [])

  // 2) Ask AI to generate a comment
  const generateComment = (id) => {
    fetch(`${API}/suggestions/${id}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_thought: "Looks promising!" })
    })
    .then(r => r.json())
    .then(json => {
      setPosts(posts.map(p =>
        p.id === id ? { ...p, suggestedComment: json.suggestedComment } : p
      ))
    })
    .catch(console.error)
  }

  // 3) Approve & post that comment
  const approveAndPost = (id) => {
    const post = posts.find(p => p.id === id)
    if (!post.suggestedComment) return alert("First click Generate Comment!")
    fetch(`${API}/suggestions/${id}/approve-and-post`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_comment: post.suggestedComment })
    })
    .then(r => r.json())
    .then(() => {
      alert("✅ Posted to Reddit!")
      setPosts(posts.filter(p => p.id !== id))
    })
    .catch(console.error)
  }

  if (posts.length === 0) return <p>No new posts right now.</p>

  return (
    <div>
      <h2>New Reddit Posts</h2>
      {posts.map(p => (
        <div key={p.id} style={{ border: "1px solid #ccc", padding: 10, margin: 10 }}>
          <h3>{p.redditPostTitle}</h3>
          <p>{p.redditPostSelftext}</p>
          <button onClick={() => generateComment(p.id)}>Generate Comment</button>
          {p.suggestedComment && (
            <>
              <p><em>AI suggests:</em> {p.suggestedComment}</p>
              <button onClick={() => approveAndPost(p.id)}>Approve & Post</button>
            </>
          )}
        </div>
      ))}
    </div>
  )
}
