-- Tabla de juegos. Se corre una vez en Supabase > SQL Editor.
create table if not exists juegos (
  id                bigint generated always as identity primary key,
  nombre            text          not null,
  plataformas       text[]        not null,
  fecha_lanzamiento date,
  precio_sugerido   numeric(6,2)  not null,
  imagen_url        text,
  url_steam         text          not null,
  url_psstore       text          not null,
  url_xbox          text,
  url_eshop         text,
  url_metacritic    text,
  url_hltb          text,
  activo            boolean       not null default true
);

-- Un juego no se puede repetir.
alter table juegos drop constraint if exists juegos_nombre_unico;
alter table juegos add constraint juegos_nombre_unico unique (nombre);

-- Cualquiera puede leer. Solo la llave secreta puede escribir.
alter table juegos enable row level security;
drop policy if exists "lectura publica" on juegos;
create policy "lectura publica" on juegos for select using (true);
