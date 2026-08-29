# User journeys

- `COMPANY_RESPONDENT`: signs in, sees only assigned assessments, autosaves, reviews, submits once, and views authorized completed results/reports.
- `COMPANY_ADMIN`: manages company profile/controller consent, creates assessments, invites participants, submits their own assigned response, generates reports and updates roadmap work.
- `CONSULTANT`: creates/repeats assessments, works the consultation requests assigned to them, reads tenant results and generates reports; company-controller settings remain with the company admin.
- `RESEARCHER`: uses only anonymized consent/origin-filtered research datasets, instrument lifecycle, statistics, quality and exports.
- `SUPER_ADMIN`: manages platform users/roles/configuration, instrument governance, research operations and audited exports.

An invited external participant opens the token, accepts required service consent and optional research consent separately, answers through the participant session, and submits once. In a multi-respondent assessment, the assessment remains in progress until every accepted participant has submitted; only then does the server calculate the shared result.

A direct participant opens the public homepage, selects “ابدأ المقياس”, records the organization demographics and four enabling conditions, accepts service consent, and starts immediately without an account or invitation. The enabling conditions are prefilled as context items, the participant answers MCM and SMCE using verbal Likert labels, and the completed single-participant case immediately displays the five-stage classification, dimension charts, and the provisional MCM–SMCE relationship interpretation.
