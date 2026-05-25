INSERT INTO tariffs (code, name, projects_limit, posts_limit, monthly_price, is_active)
VALUES
    ('lite', 'Лайт', 1, 25, 1790, true),
    ('standard', 'Стандарт', 2, 50, 3190, true)
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    projects_limit = EXCLUDED.projects_limit,
    posts_limit = EXCLUDED.posts_limit,
    monthly_price = EXCLUDED.monthly_price,
    is_active = EXCLUDED.is_active;
