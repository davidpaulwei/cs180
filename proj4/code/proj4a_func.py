import numpy as np
import matplotlib.pyplot as plt
import pickle
import torch
from animator import animator
from scipy import ndimage, interpolate
import skimage as ski
from matplotlib.patches import ConnectionPatch

# this is the functions for project 4a:

# params for perspective transformation:
LR = 1e-7 # learning rate for gradient descent.
NUM_EPOCHS = 100 # number of epochs for gradient descent.

def get_points(img_name: str, num_points: int) -> np.ndarray:
    """select and save correspondences to file."""
    img = plt.imread("media/" + img_name + ".png")
    plt.imshow(img)
    points = plt.ginput(n=num_points, timeout=0)
    points = np.array(points)[:,::-1]
    with open("media/" + img_name + "_pt.pickle", "wb") as file:
        pickle.dump(points, file)
    return points

def read_points(img_name: str) -> np.ndarray:
    """read recorded correspondences from file."""
    with open("media/" + img_name + "_pt.pickle", "rb") as file:
        points = pickle.load(file)
    return points

def show_points(img1_name: str, img2_name: str) -> None:
    """show image's correspondences."""
    img1 = plt.imread("media/" + img1_name + ".png")
    img2 = plt.imread("media/" + img2_name + ".png")
    with open("media/" + img1_name + "_pt.pickle", "rb") as file:
        img1_pts = pickle.load(file)
    with open("media/" + img2_name + "_pt.pickle", "rb") as file:
        img2_pts = pickle.load(file)
    fig = plt.figure()
    ax1 = fig.add_subplot(121)
    ax1.imshow(img1)
    ax1.plot(img1_pts[:, 1], img1_pts[:, 0], 'o', color='r', markersize=1)
    ax1.xaxis.set_visible(False)
    ax1.yaxis.set_visible(False)
    ax2 = fig.add_subplot(122)
    ax2.imshow(img2)
    ax2.plot(img2_pts[:, 1], img2_pts[:, 0], 'o', color='r', markersize=1)
    ax2.xaxis.set_visible(False)
    ax2.yaxis.set_visible(False)
    for (y1, x1), (y2, x2) in zip(img1_pts, img2_pts):
        con = ConnectionPatch(xyA=(x2, y2), xyB=(x1, y1), coordsA="data", 
                              coordsB="data", axesA=ax2, axesB=ax1, color="red")
        ax2.add_artist(con)
    plt.show()

def perspective_trans(mat: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """use given matrix to conduct perspective transformation on list of pixels."""
    vecs = mat @ np.concatenate((pts.astype(np.float32), 
                                 np.ones(len(pts))[:, None]), axis=1).T
    out_pts = vecs[:2] / vecs[2]
    return out_pts.T.astype(int)

def compute_mat(img1_pts: np.ndarray, # correspondences on image 1.
                img2_pts: np.ndarray, # correspondences on image 2.
                lr: float = None # learning rate when number of corres exceeds 4.
    ) -> np.ndarray:
    """compute perspective transformation matrix from img1 to img2.
        - when number of correspondences on each image exceeds 4, 
          an additional gradient descent will be applied to adjust the matrix."""
    # obtain matrix T by solving equation using the first 4 points.
    pt_mats = []
    for img1_pt, img2_pt in zip(img1_pts, img2_pts):
        [p1, p2], [q1, q2] = img1_pt, img2_pt
        pt_mat = np.array([
            [p1, p2, 1, 0, 0, 0, -p1*q1, -p2*q1],
            [0, 0, 0, p1, p2, 1, -p1*q2, -p2*q2],
        ])
        pt_mats.append(pt_mat)
    M = np.concatenate(pt_mats, axis=0)
    Q = img2_pts[:4].reshape(-1)
    X = np.linalg.inv(M[:8]) @ Q
    # when number of correspondences exceeds 4, 
    # use matrix calculated by the first 4 correspondneces as initial value,
    # adjusts matrix using all correspondences by gradient descent on squared-loss.
    if len(img1_pts) > 4:
        X = torch.tensor(X, requires_grad=True)
        P = torch.cat((torch.tensor(img1_pts), 
                       torch.ones(len(img1_pts))[:, None]), axis=1).T
        grf = animator(xlabel="epoch", ylabel="loss")
        for epoch in range(NUM_EPOCHS):
            T = torch.cat((X, torch.ones(1))).reshape(3, 3)
            Q = T @ P
            img2_pts_pred = Q[:2] / Q[2]
            loss = ((torch.tensor(img2_pts) - img2_pts_pred.T) ** 2).sum()
            loss.backward()
            with torch.no_grad():
                X -= X.grad * lr / (X.grad ** 2).sum().sqrt()
                X.grad.zero_()
            grf.add(epoch, loss.item())
        out_mat = T.detach().numpy()
    else:
        out_mat = np.append(X, 1).reshape(3, 3)
    return out_mat

def snap(values: np.ndarray, range: tuple) -> list:
    """snap values within range."""
    values = np.where(values < range[0], range[0], values)
    values = np.where(values > range[1], range[1], values)
    return values

def warp_img(img: np.ndarray, # input image.
             mat: np.ndarray, # perspective transform matrix.
             crop_corners: np.ndarray = None, # unless defined otherwise,
                # output image will be cropped based on image's transformed corners.
             mosaic: bool = False # when mosaic mode is on, 
                # output image will save space for the unwarped second image.
             ) -> tuple[np.ndarray, tuple]: # returns warpped image and offsets.
    """warp image according to the given perspective transformation matrix.
       - outputs: output image; offsets during transformation."""
    if mosaic:
        img_corners = np.array([[0, 0], [img.shape[0]-1, 0], 
                                [img.shape[0]-1, img.shape[1]-1], [0, img.shape[1]-1]])
        crop_corners = perspective_trans(mat, img_corners) # image transformed corners.
    min_y, max_y = crop_corners[:, 0].min(), crop_corners[:, 0].max()
    min_x, max_x = crop_corners[:, 1].min(), crop_corners[:, 1].max()
    offset_y = 0 if min_y >= 0 and mosaic else -min_y + 1
    offset_x = 0 if min_x >= 0 and mosaic else -min_x + 1
    pixel_range = ski.draw.polygon(crop_corners[:, 0] + offset_y, 
                                   crop_corners[:, 1] + offset_x)
    warpped_pixels = perspective_trans(mat, np.argwhere(img[:,:,0] >= 0)) 
    warpped_pixels += np.array([offset_y, offset_x]) # add offsets to coordinates.
    img_shape = (max(img.shape[0], max_y) + offset_y + 1, 
                 max(img.shape[1], max_x) + offset_x + 1, 3)
    out_img = np.zeros(img_shape)
    for layer_idx in range(3):
        layer_values = img[:, :, layer_idx].reshape(-1)
        interpolated_values = \
            interpolate.griddata(warpped_pixels, layer_values, pixel_range)
        out_img[pixel_range[0], pixel_range[1], layer_idx] = interpolated_values
    return out_img, (offset_y, offset_x)

def alpha_blend(img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
    """blend image 1 and image 2 using alpha blend.
       - the alpha value for each pixels is obtained by distance transformation."""
    dist1 = ndimage.distance_transform_edt(img1[:,:,0])
    dist2 = ndimage.distance_transform_edt(img2[:,:,0])
    alpha_mask = dist1 / (dist1 + dist2 + 1e-2)
    alpha_mask = np.expand_dims(alpha_mask, axis=2)
    out_img = img1 * alpha_mask + img2 * (1 - alpha_mask)
    return out_img

def mosaic(img1_name: str, img2_name: str, lr: float = None) -> np.ndarray:
    """blend img1 and img2 into a mosaic image according to their correspondences.
       - img1 is the image going to be warpped."""
    img1 = plt.imread("media/" + img1_name + ".png")[:, :, :3] + 1e-4
    img2 = plt.imread("media/" + img2_name + ".png")[:, :, :3] + 1e-4
    img1_pts, img2_pts = read_points(img1_name), read_points(img2_name)
    mat = compute_mat(img1_pts, img2_pts, lr=lr)
    out_img1, (offset_y, offset_x)= warp_img(img1, mat, mosaic=True)
    out_img2 = np.zeros(out_img1.shape)
    out_img2[offset_y:offset_y+img2.shape[0], offset_x:offset_x+img2.shape[1]] = img2
    out_img_blend = alpha_blend(out_img1, out_img2)
    out_img_blend = snap(np.where(out_img_blend == 0, 1, out_img_blend), (0, 1))
    return out_img_blend

def rectification(img_name: str) -> np.ndarray:
    """Rectificate image according to its correspondences. 
       - Idealy, the rectangular object in the image 
         will be streched into a rectangle after transformation."""
    img = plt.imread("media/" + img_name + ".png") + 1e-4
    with open("media/" + img_name + "_pt.pickle", "rb") as file:
        img_pts = pickle.load(file)
    crop_corners = np.array([[0, 0], [0, img.shape[1]-1],
                          [img.shape[0]-1, img.shape[1]-1], [img.shape[0]-1, 0]])
    rectificated_pts = np.array([
        [img.shape[0] / 6, img.shape[1] / 6],
        [img.shape[0] / 6, img.shape[1] * 5 / 6],
        [img.shape[0] * 5 / 6, img.shape[1] / 6],
        [img.shape[0] * 5 / 6, img.shape[1] * 5 / 6]
    ])
    mat = compute_mat(img_pts, rectificated_pts)
    out_img, (offset_y, offset_x) = warp_img(img, mat, crop_corners, mosaic=False)
    out_img = out_img[offset_y:, offset_x:]
    out_img = snap(np.where(out_img == 0, 1, out_img), (0, 1))
    return out_img