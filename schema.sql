create table user_data(
    chat_id integer not null primary key,
    location_number integer not null
);

pragma journal_mode = wal;
