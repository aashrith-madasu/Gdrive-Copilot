
function authenticate() {

  const authUrl = new URL("https://accounts.google.com/o/oauth2/auth");
  authUrl.searchParams.set("client_id", "609825494443-r36gpv0vjf0s7r2q680e1h89n90a48tj.apps.googleusercontent.com");
  authUrl.searchParams.set("redirect_uri", `https://${chrome.runtime.id}.chromiumapp.org`);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("scope", "https://www.googleapis.com/auth/drive.readonly");
  authUrl.searchParams.set("access_type", "offline");
  authUrl.searchParams.set("prompt", "consent");

  console.log(authUrl.href)
  
  chrome.identity.launchWebAuthFlow(
    {
      url: authUrl.href,
      interactive: true
    },
    (redirectUrl) => {
      if (chrome.runtime.lastError) {
        console.error(chrome.runtime.lastError.message);
        return;
      }

      console.log("Sucesssss", redirectUrl);

      // Parse token from redirectUrl
      const params = new URLSearchParams(new URL(redirectUrl).search);
      const code = params.get("code");
      console.log("OAuth Code:", code);

      sendCode(code);
    }
  );
}

function sendCode(code) {
  
    fetch("http://localhost:8000/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: `${code}` })
    })
    .then(res => res.json())
    .then(data => {
      console.log("sendCode response : ", data)
    })
}


function refreshIngestionStatus() {

    fetch("http://localhost:8000/ingestion_status", {
        method: "GET",
    })
    .then(res => res.json())
    .then(data => {
      console.log("ingestion status response: ", data)

      document.getElementById("status").innerHTML = `<strong> Documents ingested : ${data.ingestion_status} </strong>`

      for (let i in data.files) {
        const file = data.files[i];

        const option = document.createElement("option");
        option.value = file
        option.textContent = file;

        document.getElementById("selected-file").appendChild(option);
      }
    })

}

function submitQuery() {

  const selected_file = document.getElementById("selected-file").value;
  const query = document.getElementById("query").value;

  fetch("http://localhost:8000/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_name: selected_file, query: query })
  })
  .then(res => res.json())
  .then(data => {
    console.log("search response: ", data)

    var final_result_str = data.response

    final_result_str = final_result_str.replace(/<cite>(.*?)<\/cite>/g, '<span class="citation">$1</span>');

    document.getElementById("results").innerHTML = final_result_str
  })

}

document.getElementById("auth-btn").onclick = authenticate;
document.getElementById("refresh-btn").onclick = refreshIngestionStatus;
document.getElementById("submit-btn").onclick = submitQuery;
