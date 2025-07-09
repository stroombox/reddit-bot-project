// src/App.js
import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({});
  const [darkMode, setDarkMode] = useState(false);

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  // Toggle light / dark gradients
  const toggleDarkMode = () => {
    setDarkMode((prev) => !prev);
  };

  // Fetch the list of suggestions from your backend
  const fetchSuggestions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/suggestions`);
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();

      // Sort SMPchat posts to the top
      data.sort((a, b) => {
        const aPrio = a.subreddit.toLowerCase() === 'smpchat';
        const bPrio = b.subreddit.toLowerCase() === 'smpchat';
        if (aPrio !== bPrio) return aPrio ? -1 : 1;
        return parseInt(a.id, 10) - parseInt(b.id, 10);
      });

      setPendingComments(data);
      // Initialize the “your initial thoughts” map
      const thoughts = {};
      data.forEach((p) => (thoughts[p.id] = ''));
      setInitialThoughts(thoughts);
    } catch (e) {
      console.error('Fetch error:', e);
    }
  }, [API_URL]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  const handleInitialThoughtsChange = (id, text) => {
    setInitialThoughts((prev) => ({ ...prev, [id]: text }));
  };

  const handleGenerateSuggestion = async (id) => {
    // show spinner text
    setPendingComments((prev) =>
      prev.map((p) =>
        p.id === id ? { ...p, suggestedComment: 'Generating comment…' } : p
      )
    );

    try {
      const res = await fetch(`${API_URL}/suggestions/${id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_thought: initialThoughts[id] || '' }),
      });
      if (!res.ok) throw new Error(res.statusText);
      const { suggestedComment } = await res.json();

      setPendingComments((prev) =>
        prev.map((p) =>
          p.id === id ? { ...p, suggestedComment } : p
        )
      );
    } catch (e) {
      console.error('Generate error:', e);
      // revert on error
      fetchSuggestions();
    }
  };

  const handleAction = async (id, actionType) => {
    let url = '';
    let options = {};

    const post = pendingComments.find((p) => p.id === id);
    if (actionType === 'approve') {
      if (!post.suggestedComment.trim() || post.suggestedComment === 'Generating comment…') {
        alert('Please generate a valid comment before approving.');
        return;
      }
      url = `${API_URL}/suggestions/${id}/approve-and-post`;
      options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_comment: post.suggestedComment }),
      };
    } else if (actionType === 'reject') {
      url = `${API_URL}/suggestions/${id}`;
      options = { method: 'DELETE' };
    } else if (actionType === 'postDirect') {
      const text = initialThoughts[id] || '';
      if (!text.trim()) {
        alert('Please type your thoughts before posting directly.');
        return;
      }
      if (!window.confirm('Post your exact thoughts?')) return;
      url = `${API_URL}/suggestions/${id}/post-direct`;
      options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direct_comment: text }),
      };
    }

    try {
      const res = await fetch(url, options);
      if (!res.ok) throw new Error(res.statusText);
      // remove from queue
      setPendingComments((prev) => prev.filter((p) => p.id !== id));
    } catch (e) {
      console.error(`Action ${actionType} failed:`, e);
      alert('Something went wrong—check console and try again.');
    }
  };

  const handleEdit = (id, newText) => {
    setPendingComments((prev) =>
      prev.map((p) =>
        p.id === id ? { ...p, suggestedComment: newText } : p
      )
    );
  };

  return (
    <div className={darkMode ? 'dark-mode' : ''}>
      <button
        className="toggle-dark button button--outline"
        onClick={toggleDarkMode}
      >
        {darkMode ? 'Switch to Light' : 'Switch to Dark'}
      </button>

      <div className="container">
        <header className="backdrop-glass mb-4">
          <h1>Reddit Comment Review</h1>
        </header>

        {pendingComments.length === 0 ? (
          <p>No pending posts. Run your scraper to queue new posts.</p>
        ) : (
          pendingComments.map((c) => (
            <div key={c.id} className="backdrop-glass card mb-4 p-4">
              <div className="card-header mb-2">
                <h3>
                  <a href={c.redditPostUrl} target="_blank" rel="noopener noreferrer">
                    {c.redditPostTitle}
                  </a>
                </h3>
                <small>r/{c.subreddit}</small>
              </div>

              {c.redditPostSelftext && (
                <p className="mb-2">
                  {c.redditPostSelftext.substring(0, 150)}
                  {c.redditPostSelftext.length > 150 && '…'}
                </p>
              )}

              {c.image_urls.length > 0 && (
                <div className="image-preview-container mb-2">
                  {c.image_urls.map((u, i) => (
                    <img key={i} src={u} alt="" className="post-image-preview" />
                  ))}
                </div>
              )}

              <label>Your Initial Thoughts:</label>
              <textarea
                rows="2"
                className="p-4 mb-2"
                value={initialThoughts[c.id] || ''}
                onChange={(e) => handleInitialThoughtsChange(c.id, e.target.value)}
              />

              {c.suggestedComment ? (
                <>
                  <label>Suggested Comment:</label>
                  <textarea
                    rows="5"
                    className="p-4 mb-2"
                    value={c.suggestedComment}
                    onChange={(e) => handleEdit(c.id, e.target.value)}
                  />
                  <div>
                    <button
                      className="button button--blue mr-2"
                      onClick={() => handleAction(c.id, 'approve')}
                    >
                      Approve & Post
                    </button>
                    <button
                      className="button button--outline"
                      onClick={() => handleAction(c.id, 'reject')}
                    >
                      Reject
                    </button>
                  </div>
                </>
              ) : (
                <div>
                  <button
                    className="button button--blue mr-2"
                    onClick={() => handleGenerateSuggestion(c.id)}
                  >
                    Generate
                  </button>
                  <button
                    className="button button--outline"
                    onClick={() => handleAction(c.id, 'postDirect')}
                  >
                    Post Directly
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
