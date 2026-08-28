# Instrument DOCX import

Only a DOCX item-bank package following the contract below can become an instrument draft. The attached product specification is intentionally rejected because it is not an item bank.

The importer reads Word tables whose first cell or heading identifies `TABLE:<NAME>`. Required logical tables are:

- `INSTRUMENT_METADATA`: version and instrument metadata.
- `DIMENSIONS`: unique dimension code, construct, Arabic name and weight.
- `ITEMS`: unique item code, construct, dimension code and required Arabic wording.
- `ITEM_SETTINGS`: response type, min/max, weight, required and reverse-coded flags.
- `SCALE_VALUES`: scale values and Arabic/English labels.
- `MATURITY_LEVELS`: ordered non-overlapping MCM intervals.

Preview validates ZIP/DOCX integrity, MIME type, path traversal, XML size, duplicates, referenced dimensions, supported response types, numeric bounds, reverse coding, maturity coverage and required Arabic wording. Preview does not write. Import creates `DRAFT`; explicit approval creates `PILOT`. Empirical validation is a separate governed activity and is never inferred by the application.

Published assessments retain their original `instrument_version_id`. Duplicate copies all dimensions, scales, items, maturity levels, diagnostic rules and recommendations into a new draft; archive never deletes historical evidence.
