export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === "/") {
      return new Response("CPD Track bot Telegram API proxy. Use /bot<token>/<method>", {
        status: 200,
      });
    }

    url.protocol = "https:";
    url.host = "api.telegram.org";

    return fetch(new Request(url.toString(), request));
  },
};
