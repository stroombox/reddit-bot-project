import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({});
  const [expanded, setExpanded] = useState({});
  const [lightboxImage, setLightboxImage] = useState(null);

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  const fetchSuggestions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/suggestions`);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      
      data.sort((a, b) => {
        const aPri = a.subreddit?.toLowerCase() === 'smpchat';
        const bPri = b.subreddit?.toLowerCase() === 'smpchat';
        if (aPri && !bPri) return -1;
        if (!aPri && bPri) return 1;
        return (b.added_at || 0) - (a.added_at || 0);
      });

      setPendingComments(data);
      // Initialize state for new posts without wiping existing user input
      setInitialThoughts(prev => {
        const newThoughts = { ...prev };
        data.forEach(post => { if (newThoughts[post.id] === undefined) newThoughts[post.id] = ''; });
        return newThoughts;
      });
      setExpanded(prev => {
        const newExpanded = { ...prev };
        data.forEach(post => { if (newExpanded[post.id] === undefined) newExpanded[post.id] = false; });
        return newExpanded;
      });
    } catch (err) {
      console.error('Error fetching suggestions:', err);
    }
  }, [API_URL]);

  // This useEffect now runs only once when the app loads
  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  const handleEdit = (id, field, value) => {
    if (field === 'thoughts') {
      setInitialThoughts(prev => ({ ...prev, [id]: value }));
    } else if (field === 'suggestion') {
      setPendingComments(prev => prev.map(p => p.id === id ? { ...p, suggestedComment: value } : p));
    }
  };
  
  const toggleExpand = id => setExpanded(prev => ({ ...prev, [id]: !prev[id] }));
  const openLightbox = url => setLightboxImage(url);
  const closeLightbox = () => setLightboxImage(null);

  const handleGenerate = async id => {
    const thoughts = initialThoughts[id] || '';
    setPendingComments(prev => prev.map(p => p.id === id ? { ...p, suggestedComment: 'Generating...' } : p));
    try {
      const res = await fetch(`${API_URL}/suggestions/${id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_thought: thoughts })
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Generation failed');
      setPendingComments(prev => prev.map(p => p.id === id ? { ...p, suggestedComment: json.suggestedComment || '' } : p));
    } catch (err) {
      console.error('Generate error:', err);
      alert(`Failed to generate: ${err.message}`);
      // Revert "Generating..." on failure
      setPendingComments(prev => prev.map(p => p.id === id ? { ...p, suggestedComment: '' } : p));
    }
  };

  const handleAction = async (id, actionType) => {
    const post = pendingComments.find(p => p.id === id);
    let url = '', opts = {};

    if (actionType === 'approve') {
      if (!post.suggestedComment?.trim() || post.suggestedComment === 'Generating...') { alert('Please generate a valid comment first.'); return; }
      url = `${API_URL}/suggestions/${id}/approve-and-post`;
      opts = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved_comment: post.suggestedComment }) };
    } else if (actionType === 'reject') {
      url = `${API_URL}/suggestions/${id}`;
      opts = { method: 'DELETE' };
    } else if (actionType === 'postDirect') {
      const txt = initialThoughts[id] || '';
      if (!txt.trim()) { alert('Please enter your thoughts.'); return; }
      if (!window.confirm('Post your thoughts directly?')) return;
      url = `${API_URL}/suggestions/${id}/post-direct`;
      opts = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ direct_comment: txt }) };
    } else { return; }

    try {
      const res = await fetch(url, opts);
      if (!res.ok) throw new Error( (await res.json()).error || 'Action failed' );
      setPendingComments(prev => prev.filter(p => p.id !== id));
    } catch (err) {
      console.error('Action error:', err);
      alert(`Action failed: ${err.message}`);
    }
  };

  const renderText = (text, lineLimit) => {
    const lines = text.split('\n');
    return lines.length <= lineLimit ? text : lines.slice(0, lineLimit).join('\n') + '...';
  };

  return (
    <div className="App">
      <header className="App-header"><h1>Reddit Comment Review</h1></header>
      <div className="comment-list">
        {pendingComments.map(c => (
          <div key={c.id} className="comment-card">
            <div className="card-header">
              <div className="title-author-group">
                <a href={c.redditPostUrl} target="_blank" rel="noopener noreferrer" className="post-title">{c.redditPostTitle}</a>
                <span className="author-name">by u/{c.author}</span>
              </div>
              <span className="subreddit-tag">r/{c.subreddit}</span>
            </div>

            {c.redditPostSelftext && (
              <div>
                <p className="selftext-preview">
                  {expanded[c.id] ? c.redditPostSelftext : renderText(c.redditPostSelftext, 2)}
                </p>
                {c.redditPostSelftext.split('\n').length > 2 && 
                  <button className="see-more-button" onClick={() => toggleExpand(c.id)}>
                    {expanded[c.id] ? 'Show Less' : 'See More'}
                  </button>
                }
              </div>
            )}

            {c.image_urls && c.image_urls.length > 0 && (
              <div className="image-preview-container">
                {c.image_urls.map((url, i) => (
                  <img key={i} src={url} alt={`post content ${i+1}`} className="post-image-preview" onClick={() => openLightbox(url)} />
                ))}
              </div>
            )}
            
            <label className="textarea-label">Your Initial Thoughts:</label>
            <textarea className="initial-thoughts-textarea" placeholder="Enter thoughts for AI to polish, or leave blank..." rows={2} value={initialThoughts[c.id]} onChange={e => handleEdit(c.id, 'thoughts', e.target.value)} />
            
            {c.suggestedComment ? (
              <>                
                <label className="textarea-label">Suggested Comment:</label>
                <textarea className="suggested-textarea" rows={4} value={c.suggestedComment} onChange={e => handleEdit(c.id, 'suggestion', e.target.value)} />
                <div className="actions">
                  <button className="approve-button" onClick={() => handleAction(c.id, 'approve')}>Approve & Post</button>
                  <button className="reject-button" onClick={() => handleAction(c.id, 'reject')}>Reject</button>
                </div>
              </>
            ) : (
              <div className="actions">
                <button className="generate-button" onClick={() => handleGenerate(c.id)}>Generate Suggestion</button>
                <button className="post-direct-button" onClick={() => handleAction(c.id, 'postDirect')}>Post My Thoughts</button>
              </div>
            )}
          </div>
        ))}
      </div>
      {lightboxImage && (
        <div className="lightbox-overlay active" onClick={closeLightbox}>
          <span className="lightbox-close">&times;</span>
          <img src={lightboxImage} alt="lightbox content" />
        </div>
      )}
    </div>
  );
}

export default App;