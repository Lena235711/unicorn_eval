import numpy as np
import collections
from scipy.spatial.distance import pdist, squareform
from scipy.ndimage import binary_erosion, label
import itertools
import SimpleITK as sitk

def calculate_angle_between_lines(point1, point2, point3, point4):
    # Convert points to vectors
    vector1 = np.array([point2[0] - point1[0], point2[1] - point1[1]])
    vector2 = np.array([point4[0] - point3[0], point4[1] - point3[1]])

    # Calculate the dot product of the vectors
    dot_product = np.dot(vector1, vector2)

    # Calculate the magnitudes of the vectors
    magnitude1 = np.linalg.norm(vector1)
    magnitude2 = np.linalg.norm(vector2)

    # Calculate the cosine of the angle between the vectors
    cos_angle = dot_product / (magnitude1 * magnitude2)

    # Ensure the cosine value is within valid range [-1, 1] for arccos
    cos_angle = np.clip(cos_angle, -1, 1)

    # Calculate the angle in radians
    angle = np.arccos(cos_angle)

    # Convert the angle to degrees
    angle_degrees = np.degrees(angle)

    return angle_degrees


def find_perpendicular_diameter(point1, point2, boundary_points):
    max_distance = 0
    short_axis_points = []

    # Get all pair combinations
    bp_combinations = list(itertools.combinations(boundary_points, 2))

    angle_dev = 0
    while len(short_axis_points) == 0:
        for point3, point4 in bp_combinations:
            angle = calculate_angle_between_lines(point1, point2, point3, point4)
            # Check if the angle of the line formed by p1 and p2 is close to perpendicular
            if abs(angle - 90) < angle_dev:
                distance = np.linalg.norm(point3-point4)
                if distance > max_distance:
                    max_distance = distance
                    short_axis_points = [point3, point4]
        angle_dev += 1

    return max_distance, short_axis_points[0], short_axis_points[1]

def sape(y_true, y_pred):
    """
    Calculates the symmetric absolute percentage error between two measurements
    """
    denominator = abs(y_true) + abs(y_pred)
    if denominator == 0:
        return 0  # Return 0 if both y_true and y_pred are 0
    else:
        return abs(y_pred - y_true) / denominator

def long_and_short_axis_diameters(mask):
    """
    Function to calculate the long- and short-axis diameters of a lesion from the segmentation mask.
    Using skimage.measure.regionprops is more optimized but doesn't guarantee that both measurements
    are perpendicular to each other.
    """
    longest_z, longest_z_bp = None, None
    long_axis_diameter, short_axis_diameter = 0, 0
    long_axis_points, short_axis_points = None, None
    for z, axial_slice in enumerate(mask):
        if np.amax(axial_slice) > 0:
            labeled_seg, num_features = label(axial_slice)
            if num_features > 1:
                # Remove all but largest component
                largest_component = collections.Counter(x for x in labeled_seg.flatten() if x != 0).most_common(1)[0][0]
                labeled_seg[labeled_seg != largest_component] = 0
                labeled_seg[labeled_seg == largest_component] = 1

            # Perform erosion and subtract from the original to get boundary points
            eroded_shape = binary_erosion(labeled_seg)
            boundary_mask = labeled_seg - eroded_shape
            boundary_points = np.argwhere(boundary_mask == 1)

            # Compute all pairwise distances between boundary points
            distances = pdist(boundary_points, metric='euclidean')

            # Convert the distances to a square form
            distance_matrix = squareform(distances)

            # Find the maximum distance and the indices of the points forming the longest diameter
            long_diameter = np.max(distance_matrix)

            if long_diameter > long_axis_diameter:
                longest_z = z
                indices = np.unravel_index(np.argmax(distance_matrix), distance_matrix.shape)
                point1, point2 = boundary_points[indices[0]], boundary_points[indices[1]]
                longest_z_bp = boundary_points

                long_axis_diameter = long_diameter
                long_axis_points = [np.append(point1, z), np.append(point2, z)]

    if longest_z != None:
        # Now get the longest perpendicular short axis
        short_diameter, point3, point4 = find_perpendicular_diameter(point1, point2, longest_z_bp)
        short_axis_diameter = short_diameter
        short_axis_points = [np.append(point3, longest_z), np.append(point4, longest_z)]

    return long_axis_diameter, short_axis_diameter, long_axis_points, short_axis_points

def dice_coefficient(mask1, mask2):
    mask1 = np.asarray(mask1).astype(bool)
    mask2 = np.asarray(mask2).astype(bool)
    # Calculate intersection
    intersection = np.logical_and(mask1, mask2)
    # Calculate Dice
    dice = 2. * intersection.sum() / (mask1.sum() + mask2.sum())
    if np.isnan(dice):
        return 0
    else:
        return dice

def compute_uls_score(gts, preds):
    uls_scores = 0
    for i, gt in enumerate(gts):
        pred = preds[i]
        gt_long, gt_short, _, _ = long_and_short_axis_diameters(gt)
        pred_long, pred_short, _, _ = long_and_short_axis_diameters(pred)

        dice = dice_coefficient(gt, pred)
        sape_long = sape(gt_long, pred_long)
        sape_short = sape(gt_short, pred_short)
        uls_score = (0.888 * dice + 0.056 * (1 - min(1, sape_long))
                                    + 0.056 * (1 - min(1, sape_short)))
        uls_scores += uls_score
    
    uls_score_final = uls_scores / len(gts)
    return uls_score_final