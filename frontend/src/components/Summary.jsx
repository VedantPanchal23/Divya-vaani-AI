import { useState } from 'react';
import TextToSpeech from './TextToSpeech';
import { Icons } from './Icons';

function Summary({ summary, explanation }) {
    const [activeTab, setActiveTab] = useState('english');
    const [showExplanation, setShowExplanation] = useState(false);

    const currentSummary = activeTab === 'english' ? summary?.english : summary?.hindi;
    const currentExplanation = activeTab === 'english' ? explanation?.english : explanation?.hindi;

    return (
        <div className="summary-container">
            {/* Language Tabs */}
            <div className="language-tabs">
                <button
                    className={`language-tab ${activeTab === 'english' ? 'active' : ''}`}
                    onClick={() => setActiveTab('english')}
                >
                    <Icons.Globe size={14} />
                    English
                </button>
                <button
                    className={`language-tab ${activeTab === 'hindi' ? 'active' : ''}`}
                    onClick={() => setActiveTab('hindi')}
                >
                    <Icons.Translate size={14} />
                    हिंदी
                </button>
            </div>

            {/* Summary */}
            <div>
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: 'var(--spacing-sm)'
                }}>
                    <h4 style={{ color: 'var(--color-accent-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Icons.Summary size={18} />
                        Summary
                    </h4>
                    <TextToSpeech
                        text={currentSummary}
                        lang={activeTab === 'hindi' ? 'hi-IN' : 'en-US'}
                    />
                </div>
                <div className={`summary-content ${activeTab === 'hindi' ? 'hindi' : ''}`}>
                    {currentSummary || 'No summary available'}
                </div>
            </div>

            {/* Explanation Toggle */}
            {(explanation?.english || explanation?.hindi) && (
                <div>
                    <button
                        className="btn btn-secondary"
                        onClick={() => setShowExplanation(!showExplanation)}
                        style={{ width: '100%', justifyContent: 'center' }}
                    >
                        {showExplanation ? (
                            <>
                                <Icons.ChevronUp size={16} />
                                Hide Explanation
                            </>
                        ) : (
                            <>
                                <Icons.ChevronDown size={16} />
                                Show Detailed Explanation
                            </>
                        )}
                    </button>

                    {showExplanation && (
                        <div style={{ marginTop: 'var(--spacing-md)' }}>
                            <div style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                marginBottom: 'var(--spacing-sm)'
                            }}>
                                <h4 style={{ color: 'var(--color-accent-secondary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <Icons.Explanation size={18} />
                                    Explanation
                                </h4>
                                <TextToSpeech
                                    text={currentExplanation}
                                    lang={activeTab === 'hindi' ? 'hi-IN' : 'en-US'}
                                />
                            </div>
                            <div className={`summary-content ${activeTab === 'hindi' ? 'hindi' : ''}`}>
                                {currentExplanation || 'No explanation available'}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default Summary;
