-- Seed the 26 monitored subreddits into 7 parent groups.
-- Source of truth for the membership list: src/reddit_api/models.py:43.
-- Idempotent: re-running keeps the latest parent_id/display_name/sort_order.

INSERT INTO subreddit_categories (subreddit, parent_id, display_name, sort_order) VALUES
    ('AnthropicAI',          'ANTHROPIC',   'Anthropic',          10),
    ('ClaudeAI',             'ANTHROPIC',   'Anthropic',          10),
    ('ChatGPT',              'OPENAI',      'OpenAI',             20),
    ('OpenAI',               'OPENAI',      'OpenAI',             20),
    ('Gemini',               'GOOGLE',      'Google AI',          30),
    ('DeepMind',             'GOOGLE',      'Google AI',          30),
    ('nvidia',               'AI_INFRA',    'AI Infrastructure',  40),
    ('technology',           'AI_INFRA',    'AI Infrastructure',  40),
    ('huggingface',          'AI_INFRA',    'AI Infrastructure',  40),
    ('LocalLLaMA',           'OPEN_SOURCE', 'Open Source',        50),
    ('StableDiffusion',      'OPEN_SOURCE', 'Open Source',        50),
    ('MachineLearning',      'ML_RESEARCH', 'ML & Research',      60),
    ('DeepLearning',         'ML_RESEARCH', 'ML & Research',      60),
    ('datascience',          'ML_RESEARCH', 'ML & Research',      60),
    ('learnmachinelearning', 'ML_RESEARCH', 'ML & Research',      60),
    ('artificial',           'ML_RESEARCH', 'ML & Research',      60),
    ('ArtificialIntelligence','ML_RESEARCH','ML & Research',      60),
    ('AITA',                 'OTHER',       'Other',              70),
    ('AGI',                  'OTHER',       'Other',              70),
    ('Singularity',          'OTHER',       'Other',              70),
    ('AItools',              'OTHER',       'Other',              70),
    ('aiNews',               'OTHER',       'Other',              70),
    ('AIStartups',           'OTHER',       'Other',              70),
    ('AIArt',                'OTHER',       'Other',              70),
    ('LLMDevs',              'OTHER',       'Other',              70),
    ('PromptEngineering',    'OTHER',       'Other',              70)
ON CONFLICT (subreddit) DO UPDATE SET
    parent_id    = EXCLUDED.parent_id,
    display_name = EXCLUDED.display_name,
    sort_order   = EXCLUDED.sort_order;
