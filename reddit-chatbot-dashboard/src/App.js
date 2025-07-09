import React, { useState, useEffect, useCallback } from 'react';
import './App.css'; 

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({}); 

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  const fetchSuggestions = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/suggestions`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      let data = await response.json();

      // Prioritize r/SMPchat then by ID
      data.sort((a, b) => {
        const aIsPriority = a.subreddit.toLowerCase() === 'smpchat';
        const bIsPriority = b.subreddit.toLowerCase() === 'smpchat';
        if (aIsPriority !== bIsPriority) return aIsPriority ? -1 : 1;
        return parseInt(a.id) - parseInt(b.id);
      });

      setPendingComments(data);
      // reset thoughts
      const thoughts = {};
      data.forEach(post => { thoughts[post.id] = ''; });
      setInitialThoughts(thoughts);
    } catch (err) {
      console.error("Error fetching:", err);
    }
  }, [API_URL]);

  useEffect(() => { fetchSuggestions(); }, [fetchSuggestions]);

  const handleInitialThoughtsChange = (id, text) => {
    setInitialThoughts(prev => ({ ...prev, [id]: text }));
  };

  const handleGenerateSuggestion = async (id) => {
    const draft = initialThoughts[id] || '';
    setPendingComments(pc =>
      pc.map(p => p.id === id ? { ...p, suggestedComment: 'Generating comment...' } : p)
    );

    try {
      const res = await fetch(`${API_URL}/suggestions/${id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_thought: draft })
      });
      if (!res.ok) throw new Error();
      const json = await res.json();
      setPendingComments(pc =>
        pc.map(p => p.id === id ? { ...p, suggestedComment: json.suggestedComment } : p)
      );
    } catch (err) {
      console.error(err);
      alert("Failed to generate. Try again.");
      fetchSuggestions();
    }
  };

  const handleAction = async (id, actionType) => {
    let url, options;
    const post = pendingComments.find(p => p.id === id);

    if (actionType === 'approve') {
      if (!post.suggestedComment.trim()) return alert("Generate a comment first.");
      url = `${API_URL}/suggestions/${id}/approve-and-post`;
      options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_comment: post.suggestedComment })
      };
    }
    if (actionType === 'reject') {
      url = `${API_URL}/suggestions/${id}`;
      options = { method: 'DELETE' };
    }
    if (actionType === 'postDirect') {
      const text = initialThoughts[id] || '';
      if (!text.trim()) return alert("Type your thoughts first.");
      if (!window.confirm("Post your exact thoughts?")) return;
      url = `${API_URL}/suggestions/${id}/post-direct`;
      options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direct_comment: text })
      };
    }

    try {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error();
      setPendingComments(pc => pc.filter(p => p.id !== id));
    } catch (err) {
      console.error(err);
      alert(`Action "${actionType}" failed.`);
    }
  };

  return (
    <div className="App">
      <header className="App-header backdrop-glass">
        <h1>Reddit Comment Review</h1>
      </header>

      <div className="comment-list">
        {pendingComments.length === 0 ? (
          <p className="backdrop-glass p-4">No pending posts. Run your scraper to load new ones.</p>
        ) : (
          pendingComments.map(comment => (
            <div key={comment.id} className="comment-card">
              
              <div className="card-header mb-2">
                <h3>
                  <a href={comment.redditPostUrl} target="_blank" rel="noopener noreferrer">
                    {comment.redditPostTitle}
                  </a>
                </h3>
                <span className="subreddit-tag">r/{comment.subreddit}</span>
              </div>

              {comment.redditPostSelftext && (
                <p className="selftext-preview">{comment.redditPostSelftext.slice(0, 150)}…</p>
              )}

              {comment.image_urls.length > 0 && (
                <div className="image-preview-container">
                  {comment.image_urls.map((url, i) => (
                    <img key={i} src={url} alt={`Preview ${i+1}`} className="post-image-preview" />
                  ))}
                </div>
              )}

              <label>Your Initial Thoughts:</label>
              <textarea
                rows={2}
                placeholder="Type your draft here…"
                value={initialThoughts[comment.id]}
                onChange={e => handleInitialThoughtsChange(comment.id, e.target.value)}
              />

              {comment.suggestedComment ? (
                <>
                  <label>Suggested Comment:</label>
                  <textarea
                    rows={4}
                    value={comment.suggestedComment}
                    onChange={e => {
                      setPendingComments(pc =>
                        pc.map(p => p.id === comment.id
                          ? { ...p, suggestedComment: e.target.value }
                          : p
                        )
                      );
                    }}
                  />
                  <div className="actions">
                    <button className="button--blue" onClick={() => handleAction(comment.id, 'approve')}>
                      Approve & Send
                    </button>
                    <button className="reject-button" onClick={() => handleAction(comment.id, 'reject')}>
                      Reject
                    </button>
                  </div>
                </>
              ) : (
                <div className="actions">
                  <button className="button--blue" onClick={() => handleGenerateSuggestion(comment.id)}>
                    Generate Suggestion
                  </button>
                  <button className="button--outline" onClick={() => handleAction(comment.id, 'postDirect')}>
                    Post My Thoughts Directly
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default App;
