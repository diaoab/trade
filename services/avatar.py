"""Assistant vocal de la page Analyse : un personnage anime qui lit le resume
de l'analyse avec la synthese vocale du navigateur (Web Speech API).

Tout se passe dans le navigateur : aucune cle, aucun service externe, aucun
delai de generation. La contrepartie est que la voix depend de l'ordinateur
et du navigateur ; le texte reste affiche pour qui n'a pas de voix francaise
installee.
"""

import json


def avatar_html(sentences, theme):
    """Construit le HTML autonome de l'assistant (a passer a
    st.components.v1.html). `sentences` vient de services.narration."""

    # "</" echappe : le texte est injecte dans une balise <script>, qu'un
    # "</script>" present dans une phrase refermerait.
    payload = json.dumps(sentences, ensure_ascii=False).replace("</", "<\\/")

    return f"""
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: "Source Sans Pro", system-ui, sans-serif;
    color: {theme['text']};
    background: transparent;
  }}
  .assistant {{
    display: flex;
    gap: 16px;
    padding: 16px;
    height: 100vh;
    background: {theme['secondary_bg']};
    border: 1px solid {theme['border']};
    border-radius: 12px;
  }}
  .side {{
    flex: 0 0 150px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }}
  svg {{ width: 104px; height: 104px; }}
  .eye {{
    transform-box: fill-box;
    transform-origin: center;
    animation: blink 5s infinite;
  }}
  .mouth {{ transform-box: fill-box; transform-origin: center; }}
  .speaking .mouth {{ animation: talk 0.32s ease-in-out infinite alternate; }}
  .speaking .halo {{ animation: pulse 1.4s ease-in-out infinite; }}
  @keyframes blink {{
    0%, 94%, 100% {{ transform: scaleY(1); }}
    97% {{ transform: scaleY(0.1); }}
  }}
  @keyframes talk {{
    from {{ transform: scaleY(0.25); }}
    to {{ transform: scaleY(1.5); }}
  }}
  @keyframes pulse {{
    0%, 100% {{ opacity: 0.15; }}
    50% {{ opacity: 0.5; }}
  }}
  .buttons {{ display: flex; gap: 6px; }}
  button {{
    font: inherit;
    font-size: 13px;
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid {theme['border']};
    background: {theme['bg']};
    color: {theme['text']};
    cursor: pointer;
  }}
  button.primary {{
    background: {theme['primary']};
    border-color: {theme['primary']};
    color: {theme['bg']};
    font-weight: 600;
  }}
  button:disabled {{ opacity: 0.45; cursor: default; }}
  .transcript {{
    flex: 1;
    overflow-y: auto;
    font-size: 15px;
    line-height: 1.5;
  }}
  .transcript span {{ opacity: 0.7; }}
  .transcript span.current {{
    opacity: 1;
    background: {theme['bg']};
    border-radius: 4px;
    box-shadow: 0 0 0 3px {theme['bg']};
  }}
  .note {{ font-size: 12px; opacity: 0.7; text-align: center; }}
</style>

<div class="assistant" id="assistant">
  <div class="side">
    <svg viewBox="0 0 100 100" aria-hidden="true">
      <circle class="halo" cx="50" cy="50" r="48"
              fill="{theme['primary']}" opacity="0.15"/>
      <circle cx="50" cy="50" r="38" fill="{theme['primary']}"/>
      <ellipse class="eye" cx="37" cy="44" rx="4.5" ry="6"
               fill="{theme['bg']}"/>
      <ellipse class="eye" cx="63" cy="44" rx="4.5" ry="6"
               fill="{theme['bg']}"/>
      <ellipse class="mouth" cx="50" cy="65" rx="11" ry="4"
               fill="{theme['bg']}"/>
    </svg>
    <div class="buttons">
      <button class="primary" id="play">Écouter</button>
      <button id="stop" disabled>Arrêter</button>
    </div>
    <div class="note" id="note"></div>
  </div>
  <div class="transcript" id="transcript"></div>
</div>

<script>
  const sentences = {payload};
  const synth = window.speechSynthesis;
  const root = document.getElementById("assistant");
  const play = document.getElementById("play");
  const stop = document.getElementById("stop");
  const note = document.getElementById("note");
  const transcript = document.getElementById("transcript");

  const spans = sentences.map((sentence) => {{
    const span = document.createElement("span");
    span.textContent = sentence + " ";
    transcript.appendChild(span);
    return span;
  }});

  // Incremente a chaque lecture ou arret : les evenements d'une lecture
  // annulee arrivent apres coup et ne doivent plus toucher a l'affichage.
  let run = 0;

  function frenchVoice() {{
    const voices = synth.getVoices().filter((v) => v.lang.startsWith("fr"));
    const france = voices.filter((v) => v.lang === "fr-FR");
    // Les voix naturelles d'abord : sur macOS, la premiere voix fr-FR de la
    // liste est souvent une voix de fantaisie (Eddy, Flo...).
    return france.find((v) => /Thomas|Audrey|Aurélie|Google|Natural/.test(v.name))
      || france[0] || voices[0] || null;
  }}

  function reset() {{
    root.classList.remove("speaking");
    spans.forEach((span) => span.classList.remove("current"));
    play.textContent = "Écouter";
    stop.disabled = true;
  }}

  function speak(index, current) {{
    if (current !== run) return;
    if (index >= sentences.length) {{ reset(); return; }}

    // Une phrase par enonce : certains navigateurs coupent les enonces
    // longs au bout d'une quinzaine de secondes.
    const utterance = new SpeechSynthesisUtterance(sentences[index]);
    const voice = frenchVoice();
    utterance.lang = voice ? voice.lang : "fr-FR";
    if (voice) utterance.voice = voice;

    utterance.onstart = () => {{
      if (current !== run) return;
      spans.forEach((span) => span.classList.remove("current"));
      spans[index].classList.add("current");
      spans[index].scrollIntoView({{ block: "nearest" }});
    }};
    utterance.onend = () => speak(index + 1, current);
    utterance.onerror = () => {{ if (current === run) reset(); }};

    synth.speak(utterance);
  }}

  if (!synth) {{
    play.disabled = true;
    note.textContent = "Ce navigateur ne propose pas de synthèse vocale.";
  }} else {{
    const warn = () => {{
      note.textContent = frenchVoice()
        ? ""
        : "Aucune voix française installée : la lecture peut être "
          + "approximative.";
    }};
    // La liste des voix se charge de facon asynchrone sur Chrome.
    synth.onvoiceschanged = warn;
    warn();

    play.onclick = () => {{
      if (synth.paused) {{
        synth.resume();
        root.classList.add("speaking");
        play.textContent = "Pause";
      }} else if (synth.speaking) {{
        synth.pause();
        root.classList.remove("speaking");
        play.textContent = "Reprendre";
      }} else {{
        run += 1;
        root.classList.add("speaking");
        play.textContent = "Pause";
        stop.disabled = false;
        speak(0, run);
      }}
    }};

    stop.onclick = () => {{
      run += 1;
      synth.cancel();
      reset();
    }};

    // Changer de page ou relancer une analyse detruit ce cadre : sans cela
    // la voix continuerait a lire un resultat qui n'est plus a l'ecran.
    window.addEventListener("pagehide", () => synth.cancel());
  }}
</script>
"""
