// macOS QuickLook thumbnail extension for DWG files.
//
// Calls the Rust core (`dwg_thumbnail_png`, linked from libdwg_thumbnailer.a)
// to extract the embedded preview as PNG, then hands it to QuickLook.
//
// Add this file to a "Thumbnail Extension" target, expose the C ABI through a
// bridging header that #includes `dwg_thumbnailer.h`, and link the static lib
// (see README). QLSupportedContentTypes must list the DWG UTI (com.autodesk.dwg).

import QuickLookThumbnailing
import CoreGraphics
import ImageIO
import Foundation

final class ThumbnailProvider: QLThumbnailProvider {
    override func provideThumbnail(
        for request: QLFileThumbnailRequest,
        _ handler: @escaping (QLThumbnailReply?, Error?) -> Void
    ) {
        let maxDim = UInt32(max(request.maximumSize.width, request.maximumSize.height))

        var ptr: UnsafeMutablePointer<UInt8>? = nil
        var len: Int = 0
        let ok = request.fileURL.path.withCString { cpath in
            dwg_thumbnail_png(cpath, maxDim, &ptr, &len)
        }
        guard ok, let p = ptr, len > 0 else {
            handler(nil, nil) // no preview → QuickLook falls back
            return
        }
        let data = Data(bytes: p, count: len)
        dwg_thumbnail_free(p, len)

        guard
            let src = CGImageSourceCreateWithData(data as CFData, nil),
            let cg = CGImageSourceCreateImageAtIndex(src, 0, nil)
        else {
            handler(nil, nil)
            return
        }

        let size = CGSize(width: cg.width, height: cg.height)
        let reply = QLThumbnailReply(contextSize: size) { (ctx: CGContext) -> Bool in
            ctx.draw(cg, in: CGRect(origin: .zero, size: size))
            return true
        }
        handler(reply, nil)
    }
}
