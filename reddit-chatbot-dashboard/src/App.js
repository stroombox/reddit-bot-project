import React, { useState, useEffect, useCallback } from 'react';
import './App.css'; 

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({}); 

  // The variable for your backend URL
  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  const fetchSuggestions = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/suggestions`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      let data = await response.json();
      
      data.sort((a, b) => {
        const aIsPriority = a.subreddit && a.subreddit.toLowerCase() === 'smpchat';
        const bIsPriority = b.subreddit && b.subreddit.toLowerCase() === 'smpchat';

        if (aIsPriority && !bIsPriority) return -1;
        if (!aIsPriority && bIsPriority) return 1;

        return parseInt(a.id) - parseInt(b.id);
      });

      setPendingComments(data);

      const newThoughts = {};
      data.forEach(post => {
          newThoughts[post.id] = "";
      });
      setInitialThoughts(newThoughts);

    } catch (error) {
      console.error("Error fetching suggestions:", error);
    }
  }, [API_URL]);

  useEffect(() => {
    fetchSuggestions();
  }, [fetchSuggestions]);

  const handleInitialThoughtsChange = (id, text) => {
    setInitialThoughts(prevThoughts => ({
      ...prevThoughts,
      [id]: text
    }));
  };

  const handleGenerateSuggestion = async (id) => {
    const originalComments = [...pendingComments];
    try {
      const thoughtsForPost = initialThoughts[id] || ""; 
      setPendingComments(prev =>
        prev.map(post =>
          post.id === id ? { ...post, suggestedComment: "Generating comment..." } : post
        )
      );

      const response = await fetch(`${API_URL}/suggestions/${id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_thought: thoughtsForPost })
      });

      if (!response.ok) throw new Error("Server failed to generate comment.");
      
      const data = await response.json();

      if (data.suggestedComment) {
        setPendingComments(prev =>
          prev.map(post =>
            post.id === id ? { ...post, suggestedComment: data.suggestedComment } : post
          )
        );
      } else {
        throw new Error("LLM did not return a comment.");
      }
    } catch (error) {
      console.error("Error generating suggestion:", error);
      alert(`Failed to generate comment. Please try again.`);
      setPendingComments(originalComments);
    }
  };

  const handleAction = async (id, actionType) => {
    let url = '';
    let options = {};
    const postToProcess = pendingComments.find(post => post.id === id);

    if (actionType === 'approve') {
        if (!postToProcess || !postToProcess.suggestedComment.trim() || postToProcess.suggestedComment === "Generating comment...") {
            alert("Please generate a valid comment before approving.");
            return;
        }
        url = `${API_URL}/suggestions/${id}/approve-and-post`;
        options = {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approved_comment: postToProcess.suggestedComment })
        };
    } else if (actionType === 'reject') {
        url = `${API_URL}/suggestions/${id}`;
        options = { method: 'DELETE' };
    } else if (actionType === 'postDirect') {
        const thoughtsToPost = initialThoughts[id] || "";
        if (!thoughtsToPost.trim()) {
            alert("Please type your thoughts before posting directly.");
            return;
        }
        if (!window.confirm("Are you sure you want to post your exact thoughts directly?")) return;
        url = `${API_URL}/suggestions/${id}/post-direct`;
        options = {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ direct_comment: thoughtsToPost })
        };
    }

    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            throw new Error(`Server returned an error for action: ${actionType}`);
        }
        setPendingComments(prev => prev.filter(p => p.id !== id));
        alert(`Action '${actionType}' was successful!`);
    } catch (error) {
        console.error(`Error during '${actionType}':`, error);
        alert(`Action '${actionType}' failed. The post remains in your queue. Please try again.`);
    }
  };

  const handleEdit = (id, newText) => {
    setPendingComments(prevComments =>
      prevComments.map(post =>
        post.id === id ? { ...post, suggestedComment: newText } : post
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
          <p>No pending posts to review. Run 'python reddit_scraper.py' to find new posts.</p>
        ) : (
          pendingComments.map((comment) => (
            <div key={comment.id} className="comment-card">
              <div className="card-header">
                <h3><a href={comment.redditPostUrl} target="_blank" rel="noopener noreferrer">{comment.redditPostTitle}</a></h3>
                <span className="subreddit-tag">r/{comment.subreddit}</span>
              </div>

              {comment.redditPostSelftext && comment.redditPostSelftext.length > 0 && (
                  <p className="selftext-preview">{comment.redditPostSelftext.substring(0, 150)}{comment.redditPostSelftext.length > 150 ? '...' : ''}</p>
              )}

              {comment.image_urls && comment.image_urls.length > 0 && (
                  <div className="image-preview-container">
                      {comment.image_urls.map((imgUrl, index) => (
                          <img key={index} src={imgUrl} alt={`Post content ${index + 1}`} className="post-image-preview" onError={(e) => { e.target.onerror = null; e.target.src = "https://placehold.co/100x100?text=Img+Error"; }} />
                      ))}
                  </div>
              )}

              <p className="textarea-label">Your Initial Thoughts:</p>
              <textarea
                rows="2"
                placeholder="Type your brief response idea here for the AI..."
                value={initialThoughts[comment.id] || ""}
                onChange={(e) => handleInitialThoughtsChange(comment.id, e.target.value)}
                className="initial-thoughts-textarea"
              />

              {comment.suggestedComment ? (
                <>
                  <p className="textarea-label">Suggested Comment:</p>
                  <textarea
                    rows="5"
                    value={comment.suggestedComment}
                    onChange={(e) => handleEdit(comment.id, e.target.value)}
                  />
                  <div className="actions">
                    <button onClick={() => handleAction(comment.id, 'approve')}>Approve & Send</button>
                    <button className="reject-button" onClick={() => handleAction(comment.id, 'reject')}>Reject</button>
                  </div>
                </>
              ) : (
                <div className="actions">
                  <button className="generate-button" onClick={() => handleGenerateSuggestion(comment.id)}>Generate Suggestion</button>
                  <button className="post-direct-button" onClick={() => handleAction(comment.id, 'postDirect')}>Post My Thoughts Directly</button>
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