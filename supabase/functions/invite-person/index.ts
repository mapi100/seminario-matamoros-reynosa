import { createHandler } from "./handler.ts";
Deno.serve(createHandler(Deno.env));
