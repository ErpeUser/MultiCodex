# Sicherheitsgrenzen

## Eigene Anmeldungen

Neue Anmeldungen erfolgen ausschliesslich ueber den offiziellen Codex-App-Server (`initialize`, `account/login/start`, `account/login/completed`, `account/login/cancel`, `account/read`). MultiCodex baut kein OAuth-Protokoll nach und fragt kein Passwort ab.

Jeder Anmeldeversuch verwendet einen neuen `.sessions/<id>`-Bereich. Der offizielle Server wird mit `cli_auth_credentials_store="keyring"` gestartet. Vor Aktivierung muss ein frischer Serverprozess die gespeicherte Identitaet lesen koennen; ein auftauchendes `auth.json` blockiert die Aktivierung. Auch ein manueller Start eines verwalteten Profils prueft die Keyring-Konfiguration.

Dies ist eine Sicherheitsvorgabe und implementierte Vorpruefung, **kein Nachweis des realen Windows-Credential-Manager-Verhaltens**. Das externe Desktop-Programm ist nicht durch MultiCodex sandboxed. Seine Version, tatsaechliche Speicherung und moegliche Token-Erneuerung muessen nativ geprueft werden.

## Bestehende Daten

Verknuepfung ist keine Migration: gespeichert wird nur der explizit ausgewaehlte Profilpfad. Der Manager kopiert, verschiebt oder entschluesselt keine bestehenden Credential-Dateien. Beim Start kann die offizielle App ihre Originaldateien normal aktualisieren; die GUI weist darauf hin. Verknuepfte Profile koennen nicht durch MultiCodex neu an ein anderes Konto gebunden werden.

Die Node-Bestandsanzeige liest das bestehende v3-Pool-Dokument in einem lokalen Prozess. Dieses Dokument kann bereits Klartext-Credentials enthalten; gelesenes JSON liegt deshalb zeitweise im Prozessspeicher. Nur erlaubte Metadaten verlassen den Adapter. Die Quelle wird nicht geschrieben, kein Tokenexport erzeugt, keine CLI-Erststartmigration gestartet. Das ist keine Verschluesselung oder Uebernahme des alten Pools.

## Prozess- und Dateisicherheit

Profilpfad, Prozesskennung und Erstellungszeit werden fuer Prozessaktionen verwendet. Chromium-Kindprozesse sind keine Instanzwurzeln. Keine Beendigung nach Prozessname fuer alle Konten. Normaler Stop sendet WM_CLOSE und wartet; Zwangsbeendigung erfordert eine ausdrueckliche Benutzeraktion.

Pro-Profil-Sperren verhindern widerspruechliche Manageraktionen, eine Katalogsperre schuetzt neue Eintraege. Die Sperren werden vom Betriebssystem bei Prozessende freigegeben. Symlinks/Junctions in verwalteten Daten- und Sperrpfaden werden abgelehnt. Metadaten werden atomar ersetzt und vorher gesichert; ein Journal ermoeglicht Ruecksetzung nach unterbrochener Umschaltung. Anmeldeverzeichnisse und Credentials werden nicht automatisch geloescht, auch nicht nach einem fehlgeschlagenen Versuch.

Windows-Profilisolation ist **keine Sicherheitsgrenze gegen andere Prozesse desselben Windows-Benutzers**. Ein benuetzerspezifischer Keyring ist keine Isolation gegen Schadsoftware, die bereits unter diesem Konto laeuft. OS-Dateisperren koordinieren den Manager, nicht beliebige Fremdprogramme. Windows-ACLs, Prozessbaum-Rennen und native Keyring-Berechtigungen sind Teil der offenen Abnahme.

## Identitaet und Abbruch

Verglichen werden die normalisierte E-Mail und, sofern der offizielle Server sie liefert, die Account-ID. Ohne Account-ID ist eine separate Workspace-Zuordnung nicht bestaetigt. Gespeicherte Metadaten allein beweisen keine aktuelle Online-Gueltigkeit. `account/read` ohne Refresh darf nicht als billable/live Health-Probe ausgegeben werden.

Abbruch vor der Umschaltphase laesst die alte Zuordnung stehen. Nach Beginn der Stop/Bind/Start-Transaktion wird zuerst sicher abgeschlossen oder zurueckgesetzt; ein spaeter Abbruchwunsch ist kein garantiertes Rollback. Provider-seitige Widerrufe oder Entscheidungen der offiziellen Anwendung kann MultiCodex nicht rueckgaengig machen.

## Protokolle, Fehler und Veroeffentlichung

Keine rohen Providerantworten, OAuth-URLs oder Exception-Texte in der Benutzeroberflaeche oder den Diagnosedateien. Der Browser erhaelt nur HTTPS-Adressen auf erlaubten offiziellen Hosts. stdout ist ein lokales JSON-Protokoll, stderr des Providers wird nicht weitergereicht. Es werden keine Anmeldedaten an GitHub, Figma oder Telemetrie uebertragen.

CI verwendet nur kuenstliche Profile. Release-Nachweise duerfen keine echten Konto-, Browser- oder Token-Dumps enthalten. Keine sicherheitswidrige Quoten- oder Zugriffs-Umgehung, keine automatische Rotation.

## Technische Quellen

- https://learn.chatgpt.com/docs/auth
- https://learn.chatgpt.com/docs/app-server
- https://github.com/ndycode/codex-multi-auth/blob/main/docs/reference/public-api.md
- https://github.com/ndycode/codex-multi-auth/blob/main/docs/reference/storage-paths.md
- https://github.com/Zoltak-Dev/ai-multi-instance/blob/main/engine.py

Die Schnittstellen wurden anhand der erreichbaren Quellen untersucht. Ein Test mit der konkreten installierten Desktop-Version bleibt erforderlich.
