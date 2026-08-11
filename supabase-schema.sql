create table hr_contacts (
  id bigserial primary key,
  email text unique not null,
  domain text,
  status text check (status in ('VERIFIED','RISKY','DEAD','UNTESTED')),
  evidence text,
  company text, industry text, city text,
  role_category text, region text,
  last_contacted text, last_subject text,
  source_url text, audited_on date
);