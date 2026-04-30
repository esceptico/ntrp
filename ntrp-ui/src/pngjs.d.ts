declare module "pngjs" {
  export class PNG {
    width: number;
    height: number;
    data: Uint8Array;
    static sync: {
      read(buffer: Buffer): PNG;
    };
  }
}
