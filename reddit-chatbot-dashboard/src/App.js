import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

function formatTimestamp(utcSeconds) {
  const d = new Date(utcSeconds * 1000);
  // e.g. "Jul 8, 2025 3:45 PM"
  const date = d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
  const time = d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  });
  return `${date} ${time}`;
}

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({});

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  const fetchSuggestions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/suggestions`);
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      // Initialize thoughts state
      const thoughtsInit = {};
      data.forEach(post => { thoughtsInit[post.id] = ''; });
      setInitialThoughts(thoughtsInit);
      setPendingComments(data);
    } catch (err) {
      console.error("Error fetching suggestions:", err);
    }
  }, [API_URL]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  const handleInitialThoughtsChange = (id, text) => {
    setInitialThoughts(prev => ({ ...prev, [id]: text }));
  };

  const handleGenerateSuggestion = async (id) => {
    const userThought = initialThoughts[id] || '';
    // Optimistic UI placeholder
    setPendingComments(pc =>
      pc.map(p => p.id === id ? { ...p, suggestedComment: 'Generating…' } : p)
    );
    try {
      const res = await fetch(`${API_URL}/suggestions/${id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_thought: userThought })
      });
      if (!res.ok) throw new Error(await res.text());
      const { suggestedComment } = await res.json();
      setPendingComments(pc =>
        pc.map(p => p.id === id ? { ...p, suggestedComment } : p)
      );
    } catch (err) {
      console.error(err);
      // Rollback
      fetchSuggestions();
    }
  };

  const handleAction = async (id, actionType) => {
    let url, options;
    const post = pendingComments.find(p => p.id === id);

    if (actionType === 'approve') {
      url = `${API_URL}/suggestions/${id}/approve-and-post`;
      options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_comment: post.suggestedComment })
      };
    } else if (actionType === 'reject') {
      url = `${API_URL}/suggestions/${id}`;
      options = { method: 'DELETE' };
    } else if (actionType === 'postDirect') {
      url = `${API_URL}/suggestions/${id}/post-direct`;
      options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direct_comment: initialThoughts[id] })
      };
    }

    try {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(await res.text());
      // Remove from UI
      setPendingComments(pc => pc.filter(p => p.id !== id));
    } catch (err) {
      console.error(err);
      alert('Action failed. See console for details.');
    }
  };

  const handleEdit = (id, newText) => {
    setPendingComments(pc =>
      pc.map(p => p.id === id ? { ...p, suggestedComment: newText } : p)
    );
  };

  return (
    <div className="App">
      <header className="App-header">
        Reddit Comment Review
      </header>

      <div className="comment-list">
        {pendingComments.length === 0 ? (
          <p>No pending posts. Check back later.</p>
        ) : pendingComments.map(comment => (
          <div key={comment.id} className="comment-card">

            <div className="card-header">
              <h3>
                <a href={comment.redditPostUrl}
                   target="_blank" rel="noopener noreferrer">
                  {comment.redditPostTitle}
                </a>
              </h3>
              <span className="subreddit-tag">r/{comment.subreddit}</span>
            </div>

            {/* timestamp */}
            {comment.created_utc && (
              <div
                style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {formatTimestamp(comment.created_utc)}
              </div>
            )}

            {comment.redditPostSelftext && (
              <p className="selftext-preview">
                {comment.redditPostSelftext.length > 200
                  ? comment.redditPostSelftext.slice(0, 200) + '…'
                  : comment.redditPostSelftext}
              </p>
            )}

            {comment.image_urls?.length > 0 && (
              <div className="image-preview-container">
                {comment.image_urls.map((src, i) => (
                  <img
                    key={i}
                    className="post-image-preview"
                    src={src}
                    alt={`Attachment ${i + 1}`}
                  />
                ))}
              </div>
            )}

            <label className="textarea-label">Your Initial Thoughts:</label>
            <textarea
              className="initial-thoughts-textarea"
              rows="2"
              value={initialThoughts[comment.id] || ''}
              onChange={e =>
                handleInitialThoughtsChange(comment.id, e.target.value)
              }
            />

            {comment.suggestedComment ? (
              <>
                <label className="textarea-label">Suggested Comment:</label>
                <textarea
                  className="initial-thoughts-textarea"
                  rows="4"
                  value={comment.suggestedComment}
                  onChange={e => handleEdit(comment.id, e.target.value)}
                />
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className="generate-button"
                    onClick={() => handleAction(comment.id, 'approve')}>
                    Approve & Post
                  </button>
                  <button
                    className="post-direct-button"
                    onClick={() => handleAction(comment.id, 'reject')}>
                    Reject
                  </button>
                </div>
              </>
            ) : (
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  className="generate-button"
                  onClick={() => handleGenerateSuggestion(comment.id)}>
                  Generate Suggestion
                </button>
                <button
                  className="post-direct-button"
                  onClick={() => handleAction(comment.id, 'postDirect')}>
                  Post My Thoughts Directly
                </button>
              </div>
            )}

          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
