import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({});

  // Your backend URL (set via REACT_APP_API_URL in .env or defaults to localhost)
  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  // 1) Fetch pending Reddit posts from your Flask backend
  const fetchSuggestions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/suggestions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      let data = await res.json();

      // Move 'smpchat' posts to the top
      data.sort((a, b) => {
        const aPri = a.subreddit.toLowerCase() === 'smpchat';
        const bPri = b.subreddit.toLowerCase() === 'smpchat';
        if (aPri && !bPri) return -1;
        if (!aPri && bPri) return 1;
        return a.id.localeCompare(b.id);
      });

      setPendingComments(data);

      // Initialize a blank thought for each
      const thoughts = {};
      data.forEach(post => { thoughts[post.id] = ''; });
      setInitialThoughts(thoughts);
    } catch (err) {
      console.error('Error fetching suggestions:', err);
    }
  }, [API_URL]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  // 2) Track what the user types before asking the LLM
  const handleInitialThoughtsChange = (id, text) => {
    setInitialThoughts(prev => ({ ...prev, [id]: text }));
  };

  // 3) Call your backend to generate an AI suggestion
  const handleGenerateSuggestion = async (id) => {
    const user_thought = initialThoughts[id] || '';
    // show loading UI
    setPendingComments(prev =>
      prev.map(p =>
        p.id === id ? { ...p, suggestedComment: 'Generating comment...' } : p
      )
    );

    try {
      const res = await fetch(`${API_URL}/suggestions/${id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_thought })
      });
      if (!res.ok) throw new Error(`Gen failed ${res.status}`);
      const { suggestedComment } = await res.json();

      setPendingComments(prev =>
        prev.map(p =>
          p.id === id ? { ...p, suggestedComment } : p
        )
      );
    } catch (err) {
      console.error('Generation error:', err);
      // revert UI on error
      fetchSuggestions();
    }
  };

  // 4) Approve / reject / direct-post handler
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
      if (!initialThoughts[id].trim()) {
        return alert('Please type your thoughts before posting directly.');
      }
      if (!window.confirm('Post your exact thoughts?')) return;
      url = `${API_URL}/suggestions/${id}/post-direct`;
      options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direct_comment: initialThoughts[id] })
      };
    }

    try {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(`Action failed ${res.status}`);
      // remove from list
      setPendingComments(prev => prev.filter(p => p.id !== id));
    } catch (err) {
      console.error(`Error in ${actionType}:`, err);
      alert(`Failed to ${actionType}. Try again.`);
    }
  };

  // 5) Allow manual edits of the AI suggestion before sending
  const handleEdit = (id, newText) => {
    setPendingComments(prev =>
      prev.map(p =>
        p.id === id ? { ...p, suggestedComment: newText } : p
      )
    );
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Reddit Comment Review</h1>
      </header>

      <div className="comment-list">
        {pendingComments.length === 0 ? (
          <p>No pending posts. Run your scraper to load new ones.</p>
        ) : (
          pendingComments.map(post => (
            <div key={post.id} className="comment-card">
              <div className="card-header">
                <h3>
                  <a href={post.redditPostUrl} target="_blank" rel="noopener noreferrer">
                    {post.redditPostTitle}
                  </a>
                </h3>
                <span className="subreddit-tag">r/{post.subreddit}</span>
              </div>

              {post.redditPostSelftext && (
                <p className="selftext-preview">
                  {post.redditPostSelftext.slice(0, 150)}…
                </p>
              )}

              {post.image_urls.length > 0 && (
                <div className="image-preview-container">
                  {post.image_urls.map((url, i) => (
                    <img
                      key={i}
                      src={url}
                      alt={`Post image ${i+1}`}
                      className="post-image-preview"
                      onError={e => { e.target.src = 'https://placehold.co/100x100?text=Img+Error'; }}
                    />
                  ))}
                </div>
              )}

              <label>Your Initial Thoughts:</label>
              <textarea
                rows="2"
                placeholder="Type your idea for the AI…"
                value={initialThoughts[post.id] || ''}
                onChange={e => handleInitialThoughtsChange(post.id, e.target.value)}
                className="initial-thoughts-textarea"
              />

              {post.suggestedComment ? (
                <>
                  <label>Suggested Comment:</label>
                  <textarea
                    rows="5"
                    value={post.suggestedComment}
                    onChange={e => handleEdit(post.id, e.target.value)}
                  />
                  <div className="actions">
                    <button onClick={() => handleAction(post.id, 'approve')}>Approve & Send</button>
                    <button onClick={() => handleAction(post.id, 'reject')} className="reject-button">Reject</button>
                  </div>
                </>
              ) : (
                <div className="actions">
                  <button onClick={() => handleGenerateSuggestion(post.id)}>Generate Suggestion</button>
                  <button onClick={() => handleAction(post.id, 'postDirect')}>Post My Thoughts Directly</button>
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
