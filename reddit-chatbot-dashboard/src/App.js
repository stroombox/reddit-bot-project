import React, { useState, useEffect, useCallback } from 'react';
import './App.css'; 

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({});
  const [lightboxImage, setLightboxImage] = useState(null);

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  const fetchSuggestions = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/suggestions`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      let data = await response.json();

      data.sort((a, b) => {
        const aIsPriority = a.subreddit?.toLowerCase() === 'smpchat';
        const bIsPriority = b.subreddit?.toLowerCase() === 'smpchat';
        if (aIsPriority && !bIsPriority) return -1;
        if (!aIsPriority && bIsPriority) return 1;
        return parseInt(a.id) - parseInt(b.id);
      });

      setPendingComments(data);
      const thoughts = {};
      data.forEach(post => thoughts[post.id] = '');
      setInitialThoughts(thoughts);
    } catch (err) {
      console.error('Error fetching suggestions:', err);
    }
  }, [API_URL]);

  useEffect(() => { fetchSuggestions(); }, [fetchSuggestions]);

  const openLightbox = url => setLightboxImage(url);
  const closeLightbox = () => setLightboxImage(null);

  const handleInitialThoughtsChange = (id, text) => {
    setInitialThoughts(prev => ({ ...prev, [id]: text }));
  };

  const handleGenerate = async id => {
    const thoughts = initialThoughts[id] || '';
    setPendingComments(prev => prev.map(p => p.id === id ? { ...p, suggestedComment: 'Generating...' } : p));
    try {
      const res = await fetch(`${API_URL}/suggestions/${id}/generate`, {
        method: 'POST', 
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ user_thought: thoughts })
      });
      if (!res.ok) throw new Error();
      const json = await res.json();
      setPendingComments(prev => prev.map(p => p.id === id ? { ...p, suggestedComment: json.suggestedComment } : p));
    } catch {
      alert('Failed to generate.');
      fetchSuggestions();
    }
  };

  const handleAction = async (id, actionType) => {
    const post = pendingComments.find(p => p.id === id);
    let url = '';
    let opts = {};

    if (actionType === 'approve') {
      if (!post.suggestedComment.trim()) { alert('Please generate a comment first.'); return; }
      url = `${API_URL}/suggestions/${id}/approve-and-post`;
      opts = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved_comment: post.suggestedComment })
      };
    }

    if (actionType === 'reject') {
      url = `${API_URL}/suggestions/${id}`;
      opts = { method: 'DELETE' };
    }

    if (actionType === 'postDirect') {
      const txt = initialThoughts[id] || '';
      if (!txt.trim()) { alert('Please enter your thoughts.'); return; }
      if (!window.confirm('Post your thoughts directly?')) return;
      url = `${API_URL}/suggestions/${id}/post-direct`;
      opts = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direct_comment: txt })
      };
    }

    try {
      const res = await fetch(url, opts);
      if (!res.ok) throw new Error();
      setPendingComments(prev => prev.filter(p => p.id !== id));
    } catch {
      alert('Action failed.');
    }
  };

  return (
    <div
      className="App"
      style={{
        background: 'linear-gradient(to bottom, #000000, #333333)',
        minHeight: '100vh',
        padding: '1rem'
      }}
    >
      <header className="App-header">
        <h1 style={{ fontSize: '1.125rem', marginBottom: '1rem' }}>
          Reddit Comment Review
        </h1>
      </header>

      <div className="comment-list container">
        {pendingComments.length === 0 ? (
          <p>No pending posts to review.</p>
        ) : (
          pendingComments.map(c => (
            <div
              key={c.id}
              className="card mb-4"
              style={{
                background: 'linear-gradient(to bottom right, #1e3a8a, #3b82f6)',
                padding: '1rem',
                borderRadius: '0.5rem',
                color: '#fff',
                overflow: 'hidden'
              }}
            >
              <div className="card-header" style={{ marginBottom: '0.5rem' }}>
                <a
                  href={c.redditPostUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="post-title"
                  style={{ color: '#fff', fontWeight: 'bold', fontSize: '1rem' }}
                >
                  {c.redditPostTitle}
                </a>
                <div style={{ fontSize: '0.875rem', opacity: 0.8 }}>
                  {new Date(parseFloat(c.created_utc) * 1000).toLocaleString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit',
                    hour12: true
                  })}
                </div>
              </div>

              {c.image_urls?.length > 0 && (
                <div className="image-preview-container" style={{ marginBottom: '0.75rem' }}>
                  {c.image_urls.map((url, i) => (
                    <img
                      key={i}
                      src={url}
                      alt="post"
                      onClick={() => openLightbox(url)}
                      style={{
                        maxWidth: '100%',
                        cursor: 'pointer',
                        borderRadius: '0.25rem'
                      }}
                    />
                  ))}
                </div>
              )}

              <div style={{ marginBottom: '0.75rem' }}>
                <label style={{ display: 'block', marginBottom: '0.25rem' }}>
                  Your Initial Thoughts:
                </label>
                <textarea
                  className="initial-thoughts-textarea"
                  placeholder="Type your brief response..."
                  rows={2}
                  value={initialThoughts[c.id] || ''}
                  onChange={e => handleInitialThoughtsChange(c.id, e.target.value)}
                  style={{ width: '100%', borderRadius: '0.25rem', padding: '0.5rem' }}
                />
              </div>

              {c.suggestedComment ? (
                <>
                  <label style={{ display: 'block', marginBottom: '0.25rem' }}>
                    Suggested Comment:
                  </label>
                  <textarea
                    className="suggested-textarea"
                    rows={4}
                    value={c.suggestedComment}
                    onChange={e => setPendingComments(prev =>
                      prev.map(p =>
                        p.id === c.id ? { ...p, suggestedComment: e.target.value } : p
                      )
                    )}
                    style={{ width: '100%', borderRadius: '0.25rem', padding: '0.5rem', marginBottom: '0.75rem' }}
                  />
                  <div className="actions" style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                      className="button button--blue"
                      onClick={() => handleAction(c.id, 'approve')}
                    >
                      Approve
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
                <div className="actions" style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className="button button--blue"
                    onClick={() => handleGenerate(c.id)}
                  >
                    Generate
                  </button>
                  <button
                    className="button button--outline"
                    onClick={() => handleAction(c.id, 'postDirect')}
                  >
                    Post Direct
                  </button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {lightboxImage && (
        <div
          className="lightbox-overlay"
          onClick={closeLightbox}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
        >
          <img
            src={lightboxImage}
            alt="full"
            className="lightbox-image"
            style={{ maxHeight: '90%', maxWidth: '90%', borderRadius: '0.5rem' }}
          />
        </div>
      )}
    </div>
  );
}

export default App;
